import MySQLdb
import os
import types
import re
import subprocess
import sets
import time

from pycvsanaly2.extensions import (Extension, register_extension,
    ExtensionRunError)
from pycvsanaly2.Database import (SqliteDatabase, MysqlDatabase,
        TableAlreadyExists, statement, ICursor, execute_statement)
from pycvsanaly2.profile import profiler_start, profiler_stop
from pycvsanaly2.utils import to_utf8, printerr, printdbg, uri_to_filename
from pycvsanaly2.extensions import (Extension, register_extension,
    ExtensionRunError)

#number of source files
num_of_source = {'c':0,'java':0}
        
#search lines which contains "@@...@@"
#store information in a dict and return
#dict has a schema like this{key:[first,second,third,fourth],...}
#key means line number which contains"@@...@@"--->can not work well
#first,second,third,fourth means four int data between "@@" and "@@"   
def search_lines(patch_lines=['']):
    #dict store info which will be returned
    result={}
    #means line number
    index=0
    num_of_patch = 0
    for line in patch_lines:
        temp = line.find('@@')
        if(temp==-1):    continue
        else:
            try:
                num=line.split(',')
                first=num[0].split('-')[1]
                second=num[1].split('+')[0].split(' ')[0]
                third=num[1].split('+')[1]
                fourth=num[2].split(' ')[0]
            except IndexError, e:
                print 'list index out of range'
                raise e
                return
            result[index]=[first,second,third,fourth]
            num_of_patch +=1
            index +=1
    result['num_of_patch']=num_of_patch
    return result


#this function identify whether a patch works on a source file or not
def if_source_file(str1, str2):
    if(str1.endswith(r'.c') and str2.endswith(r'.c')):
        num_of_source['c'] +=1
        return True
    if(str1.endswith(r'.java') and str2.endswith(r'.java')):
        num_of_source['java'] +=1
        return True
    return False


#This function identify whether commit_id == 1 or not
def if_source_file_id1(str1):
    if(str1.endswith('.c')):
        return True
    if(str1.endswith('.java')):
        return True
    return False


#this function deals with source files
#extract a structure from source and store information in a dictionary
#take {1:1,2:3,3:5,4:7} for example
#this function returns dict, and caller need to check up the validity of dict
def extract_structure(lines):
    result_dict={}
    line_index = 1
    key_index = 1
    for line in lines:
        if(line.count('{')>0):
            result_dict[key_index]=line_index
            key_index +=1
        if(line.count('}')>0):
            result_dict[key_index]=line_index
            key_index +=1
        line_index +=1
    return result_dict
             

#search functions in hunks
def function_in_patch(patch):
    patch = patch.split('\n')
    cla = sets.Set()
    func = sets.Set()
    #flagenerateMinCluster(g1 means more than one row function definition
    flag1 = False
    #flag2 means this function definition maybe not be changed
    flag2 = False
    mystr = ''
    for line in patch:
        if(flag1):
            #define a Exception named cannot_analyse_patch
            #raise this kind of Exception here
            mystr = mystr + line.strip('+- ')
            if(line.count(')') > 0 and line.endswith('{')):
                flag1 = False
                func.add(func_from_str(mystr))
                mystr = ''
            #just declaration of function
            if(line.endswith(';')):
                flag1 = False
            continue
#             #unknow results
#             if(line.startswith('@@')):
#                 flag1 = False
#                 flag2 = True
        if(flag2):
            if(line.startswith('-') or line.startswith('+')):
                func.add(func_from_str(mystr))
                mystr = ''
                flag2 = False
            if(line.endswith('}')):
                flag2 = False
                mystr = ''
    
        if(line.endswith('{')):
            if(line.count('class') > 0 and line.count('{') > 0):
                cla.add(func_from_str(line))
            if(line.count('private') > 0 or
               line.count('public') > 0 or
               line.count('protected') > 0):
                if(line.count('(') > 0 and line.count(')') > 0):
                    if(line.endswith(';')):
                        continue
                    else:
                        if(line.startswith('-') or line.startswith('+')):
                            func.add(func_from_str(line))
                        else:
                            flag2 = True
                            mystr = mystr + line.strip()
                        
        if(line.count('private') > 0 or
            line.count('public') > 0 or
            line.count('protected') > 0):               
            if(line.count('(') > 0 and line.endswith(',')):
                flag1 = True
                mystr = mystr + line.strip('+- ')
                if(not(line.startswith('-') or line.startswith('+'))):
                    flag2 = True
        
    return cla, func            

   
#dictionary changed size during iteration
#A string may be contains two function definition
#This function works to separate these two function definition
def two_function_filter(funcs):
    temp = []
    temp_delete = []
    for func in funcs:
        if(func.count('private') + func.count('public') + func.count('protected') > 1):
            if(func.rfind('public') != -1):
                x = func.rfind('public')
            if(func.rfind('private') != -1):
                x = func.rfind('private')
            if(func.rfind('protected') != -1):
                x = func.rfind('protected')
            temp.append(func[0:x])
            temp.append(func[x:-1])
            
    for x in temp_delete:
        funcs.discard(x)
    for x in temp:
        funcs.add(x)
    return funcs
 
   
#extracts function definition from String
def func_from_str(mystr):
    x = mystr.find('public')
    y = mystr.find('private')
    z = mystr.find('protected')
    
    temp = max(x,y,z)
    mystr = mystr[temp:]
    mystr = mystr + '}'
    return mystr


#look up ****.odt
def oldfunc_newfunc(old_lines,new_lines,funcs):
    old_func = sets.Set()
    new_func = sets.Set()
    old_lines = ''.join(old_lines)
    new_lines = ''.join(new_lines)
    
    for func in funcs:
        x = old_lines.find(func)
        y = new_lines.find(func)
        if(x != -1):
            old_func.add(func)
        if(y != -1):
            new_func.add(func)
        if(x == -1 and y == -1):
            temp = func.find('(')
            temp = func[0:temp]
            if(old_lines.find(temp) != -1):
                old_func.add(func)
            if(new_lines.find(temp) != -1):
                new_func.add(func)
    
    return old_func, new_func


#look up ****.odtpatch
def oldcla_newcla(old_lines,new_lines,clas):
    old_cla = sets.Set()
    new_cla = sets.Set()
    old_lines = ''.join(old_lines)
    new_lines = ''.join(new_lines)
    
    for cla in clas:
        x = old_lines.find(cla)
        y = new_lines.find(cla)
        if(x != -1):
            old_cla.add(cla)
        if(y != -1):
            new_cla.add(cla)
            
    return old_cla, new_cla 


#This function extracts function and class definition from file
#This function was coded according to flow path of ****.odt
#This function can not identify the kind of function which occupies more than one rows
#I will recover it soon later. 
def function_in_file(structure, search_result, lines, tag):
    cla = sets.Set()
    func = sets.Set()
    #local variable 'temp1' referenced before assignment
    temp1 = 0
    for i in range(0,search_result['num_of_patch']):
        #print structure
        flag = False
        for k1 in structure:
            #pay attention to use of int() function
            if(int(search_result[i][tag]) == int(structure[k1])):
                #temp1 means the closest line number in source file which contains '{'
                temp1 = k1
                break
            if(int(search_result[i][tag]) < int(structure[k1])):
                temp1 = k1 - 1
                break
                    
        #following codes to extract function name
        if(temp1 == 0):
            print 'this hunk content do not in someone class definition!'
        while temp1 > 0:
            if(lines[structure[temp1]-1].endswith('{\n')):
                if(lines[structure[temp1]-1].count('class')) > 0:
                    cla.add(lines[structure[temp1]-1].strip() + '}')
                    break
                if(not flag):
                    if(lines[structure[temp1]-1].count('private') > 0 or 
                        lines[structure[temp1]-1].count('public') > 0 or
                        lines[structure[temp1]-1].count('protected') >0):
                        if(lines[structure[temp1]-1].count('(') > 0 and
                            lines[structure[temp1]-1].count(')') > 0):
                            func.add(lines[structure[temp1]-1].strip() + '}')
                            flag = True
                            
            temp1 -= 1
            if(temp1 == 0):
                print 'this hunk content do not in someone class definition!'
                break
    return cla, func


#This function is very similar to function_in_patch
def information_of_id1(patch):
    patch = patch.split('\n')
    file_old = patch[0][6:]
    file_new = patch[1][6:]
    cla = sets.Set()
    func = sets.Set()
    #flag1 means more than one row function definition
    flag1 = False
    mystr = ''
    if(if_source_file_id1(file_new)):
        for line in patch:
            if(flag1):
                #define a Exception named cannot_analyse_patch
                #raise this kind of Exception here
                mystr = mystr + line.strip('+- ')
                if(line.count(')') > 0 and line.endswith('{')):
                    flag1 = False
                    func.add(func_from_str(mystr))
                    mystr = ''
                    #just declaration of function
                if(line.endswith(';')):
                    flag1 = False

            if(line.endswith('{')):
                if(line.count('class') > 0 and line.count('{') > 0):
                    cla.add(func_from_str(line))
                if(line.count('private') > 0 or
                   line.count('public') > 0 or
                   line.count('protected') > 0):
                    if(line.count('(') > 0 and line.count(')') > 0):
                        if(line.endswith(';')):
                            continue
                        else:
                            func.add(func_from_str(line))
                        
                if(line.count('private') > 0 or
                  line.count('public') > 0 or
                  line.count('protected') > 0):               
                    if(line.count('(') > 0 and line.endswith(',')):
                        flag1 = True
                        mystr = mystr + line.strip('+- ')
    print cla,  func    
    return cla, func


#
def set_to_string(set):
    mystr = ','.join(set)
    return mystr

class Analyse_patch(Extension):
    def __init__(self):
        self.db = None

    def __create_table(self, cnn):
        cursor = cnn.cursor()

        if isinstance(self.db, SqliteDatabase):
            import sqlite3.dbapi2

            try:
                cursor.execute("""CREATE TABLE analyse_patch (
                                id integer primary key AUTOINCREMENT,
                                commit_id integer NOT NULL,
                                file_id integer NOT NULL,
                                patch_id integer NOT NULL,
                                old_class text,
                                old_function text,
                                new_class text,
                                new_function text,
                                if_id1 boolean,
                                UNIQUE(commit_id, file_id)
                                )""")
            except sqlite3.dbapi2.OperationalError:
                cursor.close()
                raise TableAlreadyExists
            except:
                raise
        elif isinstance(self.db, MysqlDatabase):
            import MySQLdb

            try:
                cursor.execute("""CREATE TABLE analyse_patch (
                                id integer primary key auto_increment,
                                commit_id integer NOT NULL REFERENCES scmlog(id),
                                file_id integer NOT NULL REFERENCES files(id),
                                patch_id integer NOT NULL REFERENCES patches(id),
                                old_class TEXT,
                                old_function TEXT,
                                new_class TEXT,
                                new_function TEXT,
                                if_id1 TINYINT,
                                UNIQUE(commit_id, file_id)
                                ) ENGINE=InnoDB, CHARACTER SET=utf8, AUTO_INCREMENT=1""")
            except MySQLdb.OperationalError, e:
                if e.args[0] == 1050:
                    cursor.close()
                    raise TableAlreadyExists
                raise
            except:
                raise

        cnn.commit()
        cursor.close()
        
    def run(self, repo, uri, db):
        #record how many patches contains different file name
        function_name_change_count = 0
        #only suitable for my computer, user can change according to your own settings
        prefix = r'/home/moqi/Downloads/voldemort'
        #old file name
        f_of_old = open('/home/moqi/Downloads/voldemort/old', 'w')
        #new file name
        f_of_new = open('/home/moqi/Downloads/voldemort/new', 'w')
        #store information returns by search_lines
        search_result={}
        #number of exception
        #such as /null and file has been deleted so that can not open
        #not accurate
        num_of_exception = 0
        #number of file which do not belong to source files
        non_source_file = 0 
        #number of patch which commit_id = 1
        num_of_id1 = 0 
        #number of files can not be recovered
        num_of_unrecovered = 0
        #old_cla contains class definition in old file
        old_cla = sets.Set()
        new_cla = sets.Set()
        old_func = sets.Set()
        new_func = sets.Set()
        #max id in table patches
        id_max = 0
        #patch_id
        patch_id = 0
        #file_id
        file_id = 0
        ##old_class, new_class, old_function, new_function
        old_class = ''
        new_class = ''
        old_function = ''
        new_function = ''
        
        
        
        __insert__ = """INSERT INTO analyse_patch (patch_id, commit_id, file_id, old_class, new_class, 
                    old_function, new_function, if_id1)
                    values (?, ?, ?, ?, ?, ?, ?, ?)"""
        start = time.time()
        
        profiler_start("Running analyse_patch extension")
        self.db = db
        self.repo = repo
        
        path = uri_to_filename(uri)
        if path is not None:
            repo_uri = repo.get_uri_for_path(path)
            ##added by me
            prefix = path
        else:
            repo_uri = uri

        path = uri_to_filename(uri)
        self.repo_uri = path or repo.get_uri()

        cnn = self.db.connect()

        cursor = cnn.cursor()
        write_cursor = cnn.cursor()
        
        cursor.execute(statement("SELECT id from repositories where uri = ?",
                             db.place_holder), (repo_uri,))
        repo_id = cursor.fetchone()[0]

        try:
            printdbg("Creating analyse_patch table")
            self.__create_table(cnn)
        except TableAlreadyExists:
            pass
        except Exception, e:
            raise ExtensionRunError(str(e))
        
        cursor.execute("select max(id) from patches")
        id_max = cursor.fetchone()
        print 'id_max = ', id_max
        #id_max = 23594 here
        id_max = id_max[0]
        
        #execute SQL sentence
        #str(id_max)
        cursor.execute("SELECT * from patches WHERE id between 1 and " + str(id_max))
        result = cursor.fetchall()
    
        #(id, commit_id, file_id, patch)---patches's schema
        for record in result:
        #fetch rev according to commit_id
            patch_id = record[0]
            file_id = record[2]
            commit_id=record[1]
            commit_id_new='%d' % commit_id
            commit_id -=1
            
            #commit_id -1 can not equals zero
            #assert commit_id != 0, 'commit_id -1 can not equals zero'
            #when commit_id equals 1, means this patch was committed with first release version of the software
            #just record and skip this loop
            if(commit_id == 0):
                num_of_id1 +=1
                new_cla, new_func = information_of_id1(record[3])
                new_class = set_to_string(new_cla)
                new_function = set_to_string(new_func)
                execute_statement(statement(__insert__,
                                            self.db.place_holder),
                                  (patch_id, commit_id_new, file_id, 'NULL', new_class, 'NULL', new_function, 1),
                                  write_cursor,
                                  db,
                                  "\nCouldn't insert, I do not know the reason at present",
                                  exception=ExtensionRunError)
                continue
        
            commit_id_old='%d' % commit_id
            
            #get rev
            cursor.execute("SELECT rev from scmlog WHERE id="+commit_id_new)
            rev_new=cursor.fetchone()[0]
            cursor.execute("SELECT rev from scmlog WHERE id="+commit_id_old)
            rev_old=cursor.fetchone()[0]
    
            #get file_old and file_new
            patch = record[3]
            patch_lines=patch.split('\n')
            try:
                search_result=search_lines(patch_lines)
            except IndexError:
                print 'this patch file is too wierd' +\
                'can not parse four number fromsubprocess its patch' +\
                'just skip this loop'
                continue
    
            file_old = patch_lines[0][6:]
            file_new = patch_lines[1][6:]
            if(not(file_old == file_new)):
            #file's name has been changed
                function_name_change_count +=1
    
            #get file content according to rev and file_new,file_old
            if(if_source_file(file_old,file_new)):
                command = 'git checkout '+rev_old+' '+file_old
                try:
                    output = subprocess.check_output(command, cwd='/home/moqi/Downloads/voldemort/', shell=True)
                except Exception, e:
                    num_of_unrecovered +=1
                    continue
                file_path_old = prefix+r'/'+file_old
                try:
                    f_old = open(file_path_old)
                except(IOError):
                    print 'can not open file'
                    num_of_exception +=1
                    continue;
                all_lines_old = f_old.readlines()
                f_of_old.writelines(all_lines_old)
            
                command = 'git checkout '+rev_new+' '+file_new
                try:
                    output = subprocess.check_output(command, cwd='/home/moqi/Downloads/voldemort/', shell=True)
                except Exception, e:
                    num_of_unrecovered +=1
                    continue
                file_path_new = prefix+r'/'+file_new
                try:
                    f_new = open(file_path_new)
                except:
                    print 'can not open file'
                    num_of_exception +=1
                    continue
                all_lines_new = f_new.readlines()
                f_of_new.writelines(all_lines_new)
                
                extract_structure_result_old=extract_structure(all_lines_old)
                extract_structure_result_new=extract_structure(all_lines_new)
                
                clas, funcs = function_in_patch(patch)
                funcs = two_function_filter(funcs)
                old_func, new_func = oldfunc_newfunc(all_lines_old, all_lines_new, funcs)
                old_cla, new_cla = oldcla_newcla(all_lines_old, all_lines_new, clas)
                
                cla, func = function_in_file(extract_structure_result_old, search_result, all_lines_old,tag=0)
                if(cla):    
                    for c in cla:
                        old_cla.add(c)
                if(func):
                    for f in func:   
                        old_func.add(f)
                    print func
                        
                cla, func = function_in_file(extract_structure_result_new, search_result, all_lines_new,tag=2)
                if(cla):    
                    for c in cla:
                        new_cla.add(c)
                if(func):
                    for f in func:   
                        new_func.add(f)
                    print func
       
            else:
                print 'is not a source file'
                non_source_file +=1
                
            print old_cla, new_cla
            print old_func, new_func
            
            old_class = set_to_string(old_cla)
            new_class = set_to_string(new_cla)
            old_function = set_to_string(old_func)
            new_function = set_to_string(new_func)
            
            execute_statement(statement(__insert__,
                                            self.db.place_holder),
                                  (patch_id, commit_id_new, file_id, old_class, new_class, old_function, new_function, 0),
                                  write_cursor,
                                  db,
                                  "\nCouldn't insert, duplicate patch?",
                                  exception=ExtensionRunError)
            #clear
            old_cla.clear()
            new_cla.clear()
            old_func.clear()
            new_func.clear()
            
        cnn.commit()
        write_cursor.close()
        cursor.close()
        cnn.close()
        profiler_stop("Running Patches extension", delete=True)
        
        end = time.time()
        print function_name_change_count, 'file change name!'
        print 'num of source file:', num_of_source
        print 'num of exception:', num_of_exception
        print 'num of non_source_file:', non_source_file    
        print 'num of files can not be recovered:', num_of_unrecovered
        print 'num_of_id1:', num_of_id1
        print 'consuming time: %ss' % str(end - start)

register_extension("Analyse_patch", Analyse_patch)
    

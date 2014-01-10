#define coded mode
#coding=utf-8

#some people said program can be executed like a script after adding this line
#however, I can not do that
#!/usr/bin/python

#import modules
import MySQLdb
import os
import types
import re

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
    num_of_patch=0
    for line in patch_lines:
        #print line
        temp = line.find('@@')
        if(temp==-1):    continue
        else:
            num=line.split(',')
            first=num[0].split('-')[1]
            second=num[1].split('+')[0].split(' ')[0]
            third=num[1].split('+')[1]
            fourth=num[2].split(' ')[0]
            result[index]=[first,second,third,fourth]
            num_of_patch +=1
            index +=1
    #print result
    result['num_of_patch']=num_of_patch
    return result

#this function identify whether a patch works on a source file or not
def if_source_file(str1,str2):
    if(str1.endswith(r'.c') and str2.endswith(r'.c')):
        globals()['num_of_source']['c'] +=1
        return True
    if(str1.endswith(r'.java') and str2.endswith(r'.java')):
        globals()['num_of_source']['java'] +=1
        return True
    return False


#this function deals with source files
#extract a structure from source and store information in a dictionary
#take {1:1,2:3,3:5,4:7} for example
#this function returns dict, and caller need to check up the validity of dict

#} else if(type instanceof JsonTypes) {
def extract_structure(lines):
    result_dict={}
    line_index = 1
    key_index = 1;
    for line in lines:
        if(line.count('{')>0):
            result_dict[key_index]=line_index
            key_index +=1
        if(line.count('}')>0):
            result_dict[key_index]=line_index
            key_index +=1
        line_index +=1
    return result_dict

#define global variables
#record how many patches contains different file name
function_name_change_count = 0
#only suitable for my computer, user can change according to your own settings
prefix =r'/home/moqi/Downloads/voldemort'
#old file name
file_old
#new file name
file_new
#store information returns by search_lines
search_result={}
#store information of how many patches a patch file contains
num_of_patch=0
#number of source files
num_of_source = {'c':0,'java':0}
#number of exception
#such as /null and file has been deleted so that can not open
#not accurate
num_of_exception = 0

#connect to MySQL
db = MySQLdb.connect(host="localhost",user="root",passwd="moqi920218 ,./",db="cvsanaly")
cursor = db.cursor()

#execute SQL sentence
cursor.execute("SELECT * from patches WHERE id BETWEEN 1 AND 50")
result = cursor.fetchall()

#(id, commit_id, file_id, patch)---patches's schema
for record in result:
    #fetch rev according to commit_id
    commit_id=record[1]
    commit_id_new='%d' % commit_id
    commit_id -=1
    #commit_id -1 can not equals zero
    assert commit_id != 0, 'commit_id -1 can not equals zero'
    commit_id_old='%d' % commit_id
    cursor.execute("SELECT rev from scmlog WHERE id="+commit_id_new)
    rev_new=cursor.fetchone()[0]
    #print rev_new
    cursor.execute("SELECT rev from scmlog WHERE id="+commit_id_old)
    rev_old=cursor.fetchone()[0]
    #print rev_old

    #get file_old and file_new
    #print record
    patch = record[3]
    #print patch
    #if (type(patch) is types.StringType):
    #    print 'type of patch:string'
    patch_lines=patch.split('\n')
    search_result=search_lines(patch_lines)
    #print patch_lines[0][6:],patch_lines[1][6:]
    file_old = patch_lines[0][6:]
    file_new = patch_lines[1][6:]
    if(not(patch_lines[0][6:] == patch_lines[1][6:])):
        #print 'function name has been changed!', record[0]
        function_name_change_count +=1

    #get file content according to rev and file_new,file_old
    #print 'git checkout '+rev_old+' '+file_old
    if(if_source_file(file_old,file_new)):
        os.system('git checkout '+rev_old+' '+file_old)
        #print prefix+r'/'+file_old
        file_path_old = prefix+r'/'+file_old
        try:
            f_old = open(file_path_old)
        except(IOError):
            #just skip this loop
            num_of_exception +=1
            continue;
        all_lines_old = f_old.readlines()
        #print all_lines_old
        #print 'cat '+file_old+' > '+r'file_old'
        #os.system('cat '+file_old+' > '+r'file_old')
        
        os.system('git checkout '+rev_new+' '+file_new)
        file_path_new = prefix+r'/'+file_new
        try:
            f_new = open(file_path_new)
        except:
            #also just skip this loop
            num_of_exception +=1
            continue;
        all_lines_new = f_new.readlines()

        #print all_lines_new
        #print 'cat '+file_new+' > '+r'file_new'
        #can not work!
        #maybe new to save before executing this sentence
        #os.system('cat '+file_new+' > '+r'file_new')
        
        extract_structure_result_old=extract_structure(all_lines_old)
        extract_structure_result_new=extract_structure(all_lines_new)
        #print extract_structure_result_new
        i,j = 0,0
        k1,k2 = 0,0
        temp1,temp2 = 0,0
        print search_result['num_of_patch']
        for i in range(0,search_result['num_of_patch']):
            while j in search_result:
                print 'j=', j
                #print search_result[j]
                
                #print extract_structure_result_old
                for k1 in extract_structure_result_old:
                    #print search_result[i][j]
                    #print extract_structure_result_old[k1]
                    #pay attention to use of int() function
                    if(int(search_result[j][0]) <= int(extract_structure_result_old[k1])):
                        #temp1 means the closest line number in source file which contains '{'
                        temp1 = k1
                        #print temp1
                        #print extract_structure_result_old[temp1]
                        break
                #following codes to extract function name
                #print all_lines_old[extract_structure_result_old[temp1]-1]
                if(temp1!=0):
                    if(all_lines_old[extract_structure_result_old[temp1]-1].endswith('{\n')):
                        print 'ends with {'
                    else:
                        print 'do not ends with {'
                while temp1 > 0:
                    if(all_lines_old[extract_structure_result_old[temp1]-1].count('class')) > 0:
                        print all_lines_old[extract_structure_result_old[temp1]-1]
                        break
                    else:
                        temp1 -= 1
                            
                for k2 in extract_structure_result_new:
                    if(int(search_result[j][2]) <= int(extract_structure_result_new[k2])):
                        temp2 = k2
                        break
                if(temp2!=0):
                    if(all_lines_new[extract_structure_result_new[temp2]-1].endswith('{\n')):
                        print 'ends with {'
                    else:
                        print 'do not ends with {'
                while temp2 > 0:
                    if(all_lines_new[extract_structure_result_new[temp2]-1].count('class')) > 0:
                        print all_lines_new[extract_structure_result_new[temp2]-1]
                        break
                    else:
                        temp2 -= 1
                j +=1
            i +=1

    #search function name in file content with first,second,third,fourth

print function_name_change_count, 'file change name!'
print num_of_source
print num_of_exception
#read patch file


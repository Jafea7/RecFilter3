#!/usr/bin/python
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import csv
import atexit
import datetime
import time
import yaml
from pathlib import Path
from nudenet import NudeDetector

MIN_PYTHON = (3, 7, 6)
if sys.version_info < MIN_PYTHON:
  sys.exit("\nPython %s.%s.%s or later is required.\n" % MIN_PYTHON)

detector = NudeDetector()

def current_time():
  return time.strftime("%H:%M:%S", time.localtime())

pushstack = []
def pushdir(dirname):
  global pushstack
  pushstack.append(os.getcwd())
  os.chdir(dirname)

def popdir():
  global pushstack
  os.chdir(pushstack.pop())

def clean_on_exit(path):
  if verbose: print('Deleting ' + str(path))
  if os.path.exists(path):
    if os.path.isdir(path):
      shutil.rmtree(path)
    else: os.remove(path)

print('\n--- RecFilter3 ---')
parser = argparse.ArgumentParser(prog='RecFilter', description='RecFilter: Remove SFW sections of videos')
parser.add_argument('file', type=str, help='Video file to process')
parser.add_argument('-i', '--interval', type=int, help='Interval between image samples (default: 5)')
#gap cut split slice separate pause break, merge bridge
parser.add_argument('-g', '--gap', type=int, help='Split segments more than x seconds apart (default: 30)')
#extension extend expand enlarge elongate stretch broaden lengthen prolong widen protrude overhang attach reach radius scope sphere area keep range zone width span radius duration size resolution adjustment
parser.add_argument('-e', '--extension', type=int, help='Extend start and end of segments by x seconds (default: 3)')
#duration minduration discard drop
parser.add_argument('-d', '--duration', type=int, help='Discard segments shorter than x seconds (default: 10)')
#startafter start begin skip
parser.add_argument('-a', '--startafter', type=int, help='Skip x seconds after beginning (default: 0)')
parser.add_argument('-b', '--stopbefore', type=int, help='Skip x seconds before finish (default: 0)')
parser.add_argument('-p', '--preset', type=str, help='Name of the config preset to use')
#category subset set group type kind class
parser.add_argument('-c', '--category', type=str, help='Category of the preset, e.g. site that the model appears on')
#wanted include match contain permit search find needed
parser.add_argument('-w', '--wanted', type=str, help='Tags being used, seperated by comma')
#unwanted unneeded exclude discard reject drop
parser.add_argument('-u', '--unwanted', type=str, help='Tags being specifically excluded, seperated by comma')
#fast quick rapid
parser.add_argument('-f', '--fast', action='store_true', help='Lower needed certainty for matches from 0.6 to 0.5 (default: False)')
#negative inverse opposite transposed sfw
parser.add_argument('-n', '--negative', default=False, action='store_true', help='Create compililation of all excluded segments too')
parser.add_argument('-l', '--logs', default=False, action='store_true', help='Keep the logs after every step (default: False)')
parser.add_argument('-k', '--keep', default=False, action='store_true', help='Keep all temporary files (default: False)')
#quiet silent batch unattended
parser.add_argument('-q', '--quiet', default=False, action='store_true', help='No user interactions. E.g. for batch processing (default: False)')
parser.add_argument('-v', '--verbose', default=False, action='store_true', help='Output working information (default: False)')
parser.add_argument('-1', '--images', action='append_const', dest='switches', const=1, help='Create sample images and allimages.txt with ffmpeg')
parser.add_argument('-2', '--analyse', action='append_const', dest='switches', const=2, help='Create analysis.txt with NudeNet AI; Requires all_images.txt')
parser.add_argument('-3', '--match', action='append_const', dest='switches', const=3, help='Create matched_images.txt; Requires analysis.txt')
parser.add_argument('-4', '--timestamps', action='append_const', dest='switches', const=4, help='Create cuts.txt; Requires matched_images.txt')
parser.add_argument('-5', '--split', action='append_const', dest='switches', const=5, help='Extract segments and create segements.txt; Requires cuts.txt')
parser.add_argument('-6', '--save', action='append_const', dest='switches', const=6, help='Connect segements and save final result; Requires segments.txt')

args = parser.parse_args()

#Only really use category when preset given
if args.preset:
  preset = args.preset.lower()
  if args.category: category = args.category.lower()
  else: category = False
else:
  preset = 'default'
  if args.category: preset = args.category.lower()
  else: category = False


video_name = Path(args.file)
keep = args.keep
logs = args.logs
verbose = args.verbose
create_negative = args.negative
quiet = args.quiet
keep_filedate = True

# Default wanted is gender neutral, if a particular gender is required it can be entered into the config file per preset
# Other terms can also be set in the config, see https://github.com/Jafea7/RecFilter3 for valid terms
wanted = ['EXPOSED_BREAST', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS', 'EXPOSED_GENITALIA', 'EXPOSED_BELLY']
unwanted = []
file_ext = 'mp4' # In case there's no videoext entry in the config

print('\n' + current_time() + ' INFO:  Input file: ')
print(str(video_name))


#Keep track of used arguments and initialize variables for unused ones
commandline = {}
if args.interval:
  sample_interval = args.interval
  commandline['interval'] = args.interval
else: sample_interval = 5
if args.gap:
  segment_gap = args.gap
  commandline['gap'] = args.gap
else: segment_gap = 30
if args.duration:
  min_segment_duration = args.duration
  commandline['duration'] = args.duration
else: min_segment_duration = 10
if args.extension:
  segment_extension = args.extension
  commandline['extension'] = args.extension
else: segment_extension = 3
if args.startafter:
  skip_begin = args.startafter
  commandline['startafter'] = args.startafter
else: skip_begin = 0
if args.stopbefore:
  skip_finish = args.stopbefore
  commandline['stopbefore'] = args.stopbefore
else: skip_finish = 0
if args.wanted:
  wanted = args.wanted.split(',')
  commandline['include'] =  args.wanted
if args.unwanted:
  unwanted = args.unwanted.split(',')
  commandline['exclude'] =  args.unwanted
if args.fast:
  fastmode = args.fast
  commandline['fastmode'] =  args.fast
else: fastmode = False

#Load config
config_path = Path(os.path.splitext(sys.argv[0])[0] + '.config')
if config_path.exists() == False:
  print('\nWARN:  No config file \'%s\' found.' % config_path)
else:
  try:
    with open(config_path,"r") as f:
      config = yaml.safe_load(f)
      config_valid = True
  except Exception as config_error: 
    print('\nERROR:  Config file ' + str(config_path) + ' is invalid. The following error occured: ')
    print(config_error)
    config_valid = False
  if config_path.exists() == False or config_valid == False:
      print("Do you you want to continue with default arguments instead?")
      print('[y/n] ')
      stop = False
      while stop == False:
        answer = str( input().lower().strip() )
        if answer == 'y':
          stop = True
        elif answer == 'n':
          stop = True
          sys.exit()
        else: print("Please enter y or n.")


list_of_valid_config_keys = ['note','inherit','interval','gap','duration','extension','category','include','exclude','startafter','stopbefore','filesuffix','videoext','fastmode','destination','move_original','rename_identical','move_identical','rename_noresult','move_noresult','move_segments','move_txt_files','confirm_overwrite','confirm_defaults','create_noresult_txt','create_identical_txt','keep_filedate']
main_settings_list = ['interval','gap','duration','extension','include','exclude','fastmode']
main_settings = []
other_settings = []

#Ouput command line settings
for key, value in commandline.items():
  if key in main_settings_list:
    main_settings.append(('commandline',key,value))
  else: other_settings.append(('commandline',key,value))

if config_valid and preset:

#Used lists
  presets_found = []
  filesuffix_list = []
  inconfig = []

#Check whether the value hasn't been set already by a higher priority preset
  def write_config_value(key,type):
    #Check whether key exists for preset
    if preset_dict.get(key) is not None:
      if type != 'path':
        if isinstance(preset_dict.get(key),type):
          #Don't overwrite values given via command line
          if (key in commandline) == False:
            #Inherit has to be allowed. Otherwise it prevents a second inherit.
            if ((key in inconfig) == False) or (key == 'inherit') or (key == 'filesuffix'):
              inconfig.append(key)
              if key in main_settings_list:
                main_settings.append((preset_name,key,preset_dict.get(key)))
              else: other_settings.append((preset_name,key,preset_dict.get(key)))
              return True
            else: return False
          else: return False
        else: sys.exit('\nERROR:  ' + key + ' in preset ' + preset_name + ' needs to be ' + str(type))
    else: return False

#Check config keys for typos
  for i in list(config.items()):
    for j in i[1]:
      if j in list_of_valid_config_keys: pass
      else: sys.exit('\nERROR:  Config key ' + j + ' is invalid. Check for typos.')

#Loop through all the config presets
  inherit = ''
  i = 0
  while i < 2:
    justinherited = False #reset re-loop trigger
    for preset_name,preset_dict in config.items():
      #skip presets that have already been applied
      if (preset_name in presets_found) == False:
        if (preset_name == preset) or (preset_name == inherit):
          #reset inherit to an empty string once we were able to use it to get into the right preset
          if preset_name == inherit: inherit = ''
          #if category is used, the category has to match, otherwise only inherit allows entry
          if (category == False) or (category and preset_dict.get('category') == category):
            if write_config_value('inherit',str):
              inherit = preset_dict.get('inherit')
              justinherited = True #trigger to rerun preset loop
            if write_config_value('code',str): code = preset_dict.get('code')
            if write_config_value('interval',int): sample_interval = preset_dict.get('interval')
            if write_config_value('gap',int): segment_gap = preset_dict.get('gap')
            if write_config_value('extension',int): segment_extension = preset_dict.get('extension')
            if write_config_value('duration',int): min_segment_duration = preset_dict.get('duration')
            if write_config_value('include',str): wanted = preset_dict.get('include').split(',')
            if write_config_value('exclude',str): unwanted = preset_dict.get('exclude').split(',')
            if write_config_value('startafter',int): skip_begin = preset_dict.get('startafter')
            if write_config_value('stopbefore',int): skip_finish = preset_dict.get('stopbefore')
            if write_config_value('filesuffix',str): filesuffix_list.append(preset_dict.get('filesuffix'))
            if write_config_value('code_suffix',bool): code_suffix = preset_dict.get('code_suffix')
            if write_config_value('videoext',str): file_ext = preset_dict.get('videoext')
            if write_config_value('fastmode',bool): fastmode = preset_dict.get('fastmode')
            if write_config_value('destination','path'): destination = preset_dict.get('destination')
            if write_config_value('tempdir','path'): tempdir = preset_dict.get('tempdir')
            if write_config_value('move_original','path'): move_original = preset_dict.get('move_original')
            if write_config_value('move_tempdir','path'): move_tempdir = preset_dict.get('move_tempdir')
            if write_config_value('rename_identical','path'): rename_identical = preset_dict.get('rename_identical')
            if write_config_value('move_identical','path'): move_identical = preset_dict.get('move_identical')
            if write_config_value('rename_noresult','path'): rename_noresult = preset_dict.get('rename_noresult')
            if write_config_value('move_noresult','path'): move_noresult = preset_dict.get('move_noresult')
            if write_config_value('move_segments','path'): move_segments = preset_dict.get('move_segments')
            if write_config_value('move_txt_files','path'): move_segments = preset_dict.get('move_segments')
            if write_config_value('confirm_overwrite',bool): confirm_overwrite = preset_dict.get('confirm_overwrite')
            if write_config_value('confirm_defaults',bool): confirm_defaults = preset_dict.get('confirm_defaults')
            if write_config_value('create_noresult_txt',bool): create_noresult_txt = preset_dict.get('create_noresult_txt')
            if write_config_value('create_identical_txt',bool): create_identical_txt = preset_dict.get('create_identical_txt')
            if write_config_value('create_contact_sheet',bool): create_contact_sheet = preset_dict.get('create_contact_sheet')
            if write_config_value('keep_filedate',bool): keep_filedate = preset_dict.get('keep_filedate')
            #note down used presets, so we can skip them
            presets_found.append(preset_name)
            #stop the loop once default was applied as a last possible inheritance
            if 'default' in presets_found: break
    #if it was the last preset and no inheritance has been set, inherit the default preset
    if (i == 1) and inherit == '':
      inherit = 'default'
      justinherited = True
    #If a preset inherits look through all presets again
    if justinherited: i = 0
    else: i+=1
 
  if preset.lower() not in presets_found:
    print('\n' + current_time() + ' INFO:  Preset \'' + preset + '\' not found.')
    if (not quiet):
      print("\nThere might be a typo in your --preset argument.\nDo you want to continue with default settings instead?")
      print('[y/n] ')
      stop = False
      while stop == False:
        answer = str( input().lower().strip() )
        if answer == 'y':
          stop = True
          print('Using defaults')
        elif answer == 'n':
          stop = True
          sys.exit()
        else: print("Please enter y or n.")
    if quiet and (not confirm_defaults): sys.exit('confirm_defaults = False')

print('\n' + current_time() + ' INFO:  Using the following settings:')

#Find longest key name for formatting the output
max_key_len = 0
for i in range(0,len(list_of_valid_config_keys)):
  if len(list_of_valid_config_keys[i]) > max_key_len:
      max_key_len = len(list_of_valid_config_keys[i])

#Find longest preset name for formatting the output
max_presetname_len = 0
def find_longest_preset_name(tuple):
  global max_presetname_len
  for setting in tuple:
    if len(setting[0]) > max_presetname_len:
      max_presetname_len = len(setting[0])

find_longest_preset_name(main_settings)
find_longest_preset_name(other_settings)

def settings_output(title,tuple):
  print(title)
  for setting in tuple:
    #split up tags to not use up too much space
    if setting[1] == ('include' or 'exclude'):
      split_tags = format(setting[2]).split(',')
      for tag in split_tags:
        print('Preset: ' + format(str(setting[0]) + '  ').ljust(max_presetname_len+2,'-')[:30] + ('>  ' + str(setting[1]) + ': ').rjust(max_key_len+5,'-') + str(tag))
    else: print('Preset: ' + format(str(setting[0]) + '  ').ljust(max_presetname_len+2,'-')[:30] + ('>  ' + str(setting[1]) + ': ').rjust(max_key_len+5,'-') + str(setting[2]))

settings_output('\nMain Settings:',main_settings)

tag_codes = [
(["01"],"EXPOSED_ANUS"),
(["02"],"EXPOSED_ARMPITS"),
(["03"],"COVERED_BELLY"),
(["04"],"EXPOSED_BELLY"),
(["05"],"COVERED_BUTTOCKS"),
(["06"],"EXPOSED_BUTTOCKS"),
(["07"],"FACE_F"),
(["08"],"FACE_M"),
(["09"],"COVERED_FEET"),
(["10"],"EXPOSED_FEET"),
(["11"],"COVERED_BREAST_F"),
(["12"],"EXPOSED_BREAST_F"),
(["13"],"COVERED_GENITALIA_F"),
(["14"],"EXPOSED_GENITALIA_F"),
(["15"],"EXPOSED_BREAST_M"),
(["16"],"EXPOSED_GENITALIA_M"),
(["07","08"],"FACE"),
(["12","15"],"EXPOSED_BREAST"),
(["14","16"],"EXPOSED_GENITALIA")
]

used_integers = []
wanted_tag_codes = []
unwanted_tag_codes = []

for j in main_settings:
  if j[1] == 'interval':
    used_integers.append('i'+str(j[2]))
  if j[1] == 'gap':
    used_integers.append('g'+str(j[2]))
  if j[1] == 'duration':
    used_integers.append('d'+str(j[2]))
  if j[1] == 'extension':
    used_integers.append('e'+str(j[2]))
  if j[1] == 'fastmode':
    if j[2] == True: used_integers.append('f1')
  if j[1] == 'include':
    for k in j[2].split(','):
      for i in tag_codes:
        if k == i[1]: wanted_tag_codes = wanted_tag_codes + i[0]
  if j[1] == 'exclude':
    for l in j[2].split(','):
      for m in tag_codes:
        if l == m[1]: unwanted_tag_codes = unwanted_tag_codes + m[0]

version = 'v1'
wanted_char = 'w'
if unwanted_tag_codes:
  unwanted_char = 'u'
else:
  unwanted_char = ''
code = version + ''.join(sorted(used_integers,reverse=True)) + wanted_char + ''.join(sorted(list(set(wanted_tag_codes)))) + unwanted_char + ''.join(sorted(list(set(unwanted_tag_codes)))) + version

print('\nThe Main Settings can be identified and reused with this code: ')
print(code)

settings_output('\nOther Settings:',other_settings)

#Check tags for typos
valid_tags = [
"EXPOSED_ANUS",
"EXPOSED_ARMPITS",
"COVERED_BELLY",
"EXPOSED_BELLY",
"COVERED_BUTTOCKS",
"EXPOSED_BUTTOCKS",
"FACE_F",
"FACE_M",
"COVERED_FEET",
"EXPOSED_FEET",
"COVERED_BREAST_F",
"EXPOSED_BREAST_F",
"COVERED_GENITALIA_F",
"EXPOSED_GENITALIA_F",
"EXPOSED_BREAST_M",
"EXPOSED_GENITALIA_M",

"FACE",
"EXPOSED_BREAST",
"EXPOSED_GENITALIA"
]

if wanted[0] == 'NONE':
  sys.exit('No tags to match specified. At least one Tag must be specified.')
else:
  for i in wanted:
    if i in valid_tags: pass
    else: sys.exit('\nERROR:  Tag ' + i + ' is invalid. Check for typos.')
  for j in unwanted:
    if i in valid_tags: pass
    else: sys.exit('\nERROR:  Tag ' + j + ' is invalid. Check for typos.')

imagelist = []
lines = []
beginnings = []
endings = []

i = 0
b = None
e = 0
p = 0
z = 0

keyframe_interval = 1

#Path variables
video_path = Path(video_name).resolve() # Get the full video path
startdir = Path(video_path).parent
tmpdirnaming = '~' + Path(video_name).stem
tmpdir = Path(startdir).joinpath(tmpdirnaming)
images_dir = Path(tmpdir) / 'images'
segments_dir = Path(tmpdir) / 'segments'
excluded_segments_dir = Path(tmpdir) / 'excluded_segments'

#Get modification time from the original
modification_time = os.stat(video_path).st_mtime_ns

# Change to video container directory
pushdir(Path(video_path).parent) 

#Finding video duration
ffprobe_cmd = subprocess.check_output('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -i "' + str(video_path) + '"', shell=True).decode()
duration_float = round(float(ffprobe_cmd),3)
duration = int(round(duration_float))
if verbose:
  print('\n' + current_time() + ' INFO:  Duration of input video: ')
  print(str(duration) + ' seconds')

# Activation and deactivation of whole program sections
try:
  if len(args.switches) > 0:
    code_sections = []
    #prevent user from skipping inbetween steps when naming more than one program section
    args.switches.sort()
    for i in range(args.switches[0], args.switches[-1] + 1):
      code_sections.append(i)
    print('\n' + current_time() + ' INFO:  Execution restricted by user:')
    print('Only the following program steps will be processed:')
    if 1 in code_sections: print('- Step 1 of 6: Creation of image samples')
    if 2 in code_sections: print('- Step 2 of 6: Analysis through NudeNet AI')
    if 3 in code_sections: print('- Step 3 of 6: Find tags')
    if 4 in code_sections: print('- Step 4 of 6: Find cut markers')
    if 5 in code_sections: print('- Step 5 of 6: Extract segments at cut markers')
    if 6 in code_sections: print('- Step 6 of 6: Connect segments and save final result')
    logs = True
    print('\n' + current_time() + ' INFO:  Option --logs was set to true automatically:')
    print('Text files will be kept as input for further processing.')
#if the user didn't specify any sections run all sections
except: code_sections = [1,2,3,4,5,6]

# Creation of temporary folders
print('\n' + current_time() + ' INFO:  Creating temporary directory ...')
if Path(tmpdir).exists():
    print('WARN:  The following temporary folder will be overwritten:')
    print(os.path.abspath(tmpdir))
    if (not quiet):
      print('\nAre you sure you want to potentially overwrite previous results?')
      print('[y/n] ')
      stop = 0
      while stop == 0:
        answer = str( input().lower().strip() )
        if answer == 'y':
          stop = 1
        elif answer == 'n':
          sys.exit('Creation of the temporary directory failed')
          stop = 1
        else: print("Please enter y or n.")
    else:
      if quiet and (not confirm_overwrite): sys.exit('confirm_overwrite = False')
else:
  try:
    os.mkdir(tmpdir)
    print(current_time() + ' INFO:  Created temporary directory')
  except OSError: sys.exit('Creation of the temporary directory failed')
print('\n')

#Delete tmpdir again after program termination
if keep == False and logs == False: atexit.register(clean_on_exit,tmpdir)

# Filenames used
all_images_txt_path = os.path.join(tmpdir, 'all_images.txt')
analysis_txt_path = os.path.join(tmpdir, 'analysis.txt')
matched_images_txt_path = os.path.join(tmpdir, 'matched_images.txt')
cuts_txt_path = os.path.join(tmpdir, 'cuts.txt')
segments_txt_path = os.path.join(tmpdir, 'segments.txt')
excluded_segments_txt_path = os.path.join(tmpdir, 'excluded_segments.txt')
if filesuffix_list: addtofilename = ''.join(reversed(filesuffix_list)).replace(' ', '_')
else: addtofilename = ''

def recreate(txt,dir = None):
  if dir is not None:
    #Delete previously created folder to rerun steps
    if Path(dir).exists(): shutil.rmtree(dir)
    os.mkdir(dir)
  #Delete previously created output txt to rerun steps
  if Path(txt).exists(): os.remove(txt)
  #Delete txt again in case of program termination
  if keep == False and logs == False: atexit.register(clean_on_exit,txt)


if 1 in code_sections: #on/off switch for code
  if fastmode: max_side_length = 800
  else: max_side_length = 1280
  if fastmode: print(current_time() + ' INFO:  Step 1 of 6: Fast mode activated:')
  if fastmode: print(current_time() + ' INFO:  Step 1 of 6: Images will be resized to a max side length of ' + str(max_side_length) )
  print(current_time() + ' INFO:  Step 1 of 6: Creating sample images with ffmpeg...')

#Create clean folders/files
  recreate(all_images_txt_path,images_dir)
  os.chdir(images_dir)

#ffmpeg image creation
  with open(all_images_txt_path,"w", newline='') as all_images_txt:
    image_ffmpeg_filenames = '%07d.jpg'
    image_ffmpeg_inputpath = '-i "'+ str(video_path) + '"'
    if fastmode: image_ffmpeg_resize = "',scale=\'" + str(max_side_length) + ":" + str(max_side_length) + ":force_original_aspect_ratio=decrease\'"
    else: image_ffmpeg_resize = "',scale=\'" + str(max_side_length) + ":" + str(max_side_length) + ":force_original_aspect_ratio=decrease\'"
    if skip_finish: image_ffmpeg_stop = ' -t ' + str(duration_float)-skip_finish
    else: image_ffmpeg_stop =  ' '
    image_ffmpeg_inputoptions = ' -y -skip_frame nokey -copyts -start_at_zero -ss ' + str(skip_begin)
    #showinfo has to be used before and after the fps function to get correct timestamps
    image_ffmpeg_filters = ' -vf "showinfo,fps=1,select=\'not(mod(t,' + str(sample_interval) + '))' + image_ffmpeg_resize + ',showinfo"'
    image_ffmpeg_outputoptions = image_ffmpeg_stop + ' -vsync 0 -an -qmin 1 -q:v 1'
    image_ffmpeg_cmd = 'ffmpeg' + image_ffmpeg_inputoptions + ' ' + image_ffmpeg_inputpath + image_ffmpeg_filters + image_ffmpeg_outputoptions + ' ' + image_ffmpeg_filenames

    

   #Create other images with ffmpeg fps filter
    if verbose: print(image_ffmpeg_cmd)
    #For some reason ffmpeg sends its showinfo output to stderr instead of stdout
    image_ffmpeg_output = subprocess.run(image_ffmpeg_cmd,check=True,capture_output=True,text=True)

   #Identify image timestamps
   # https://stackoverflow.com/questions/51325158/ffmpeg-timestamp-information-using-fps-filter-isnt-aligned-with-ffprobe
    image_timestamps = []
    input_frames_lines = []
    fps_filter_frames_lines = []
    input_table = {}
    output_positions = []

    for line in image_ffmpeg_output.stderr.splitlines():
      if ('Parsed_showinfo_0' in line) and ('pts_time' in line):
        input_frames_lines.append(line)
      elif ('Parsed_showinfo_') in line and ('pts_time' in line):
        fps_filter_frames_lines.append(line)

    for line in input_frames_lines:
      input_timestamp = re.search(r' pts_time:[ ]*([0-9\.]+) ',str(line)).group(1)
      input_position = re.search(r' pos:[ ]*([0-9]+) ',str(line)).group(1)
      if input_timestamp and input_position:
#        input_table.append([input_timestamp,input_position])
        input_table[input_position] = input_timestamp
    for line in fps_filter_frames_lines:
      output_position = re.search(r' pos:[ ]*([0-9]+) ',str(line)).group(1)
      if output_position: output_positions.append(output_position)
    for pos in output_positions:
      image_timestamps.append(input_table[pos])

    
   #Create an exact last image (not a keyframe)
   # https://superuser.com/a/1448673
    if skip_finish:
      'ffmpeg' + ' -y -copyts -start_at_zero -sseof -' + skip_finish + ' ' + image_ffmpeg_inputpath + ' ' + image_ffmpeg_stop + ' -vframes 1 -vf "showinfo" -vsync 0 -an -qmin 1 -q:v 1' + ' ' + str(len(image_timestamps)+1).zfill(7) + '.jpg'
    else: 
      image_ffmpeg_last_cmd = 'ffmpeg' + ' -y -copyts -start_at_zero -sseof -0.1' + ' ' + image_ffmpeg_inputpath  + ' -update 1 -vf "showinfo" -vsync 0 -an -qmin 1 -q:v 1' + ' ' + str(len(image_timestamps)+1).zfill(7) + '.jpg'
    if verbose: print(image_ffmpeg_first_cmd)
    image_ffmpeg_last_output = subprocess.run(image_ffmpeg_last_cmd,check=True,capture_output=True,text=True)
    for line in image_ffmpeg_last_output.stderr.splitlines():
      if ('Parsed_showinfo_') in line and ('pts_time' in line):
        last_timestamp = re.search(r' pts_time:[ ]*([0-9\.]+) ',str(line)).group(1)
    if last_timestamp > image_timestamps[-1]:
      image_timestamps.append(last_timestamp)
    else: os.remove(str(len(image_timestamps)+1).zfill(7) + '.jpg')

    image_csv = csv.writer(all_images_txt,delimiter=' ')
    file_list = [f for f in os.listdir(images_dir) if re.search(r'[0-9]{7}.jpg', f)]
    image_count = 0
    for file in file_list:
      image_csv.writerow([image_timestamps[image_count],file])
      if verbose: print(file)
      image_count +=1
  print(current_time() + ' INFO:  Step 1 of 6: Finished creating ' + str(image_count) + ' sample images.\n')    
  os.chdir(startdir)


if 2 in code_sections: #on/off switch for code
  if fastmode: print(current_time() + ' INFO:  Step 2 of 6: Fast mode for NudeNet was activated')
  print(current_time() + ' INFO:  Step 2 of 6: Analysing images with NudeNet ...')

#Create clean folders/files
  recreate(analysis_txt_path)
  os.chdir(images_dir)

  #Delete previously created output to rerun steps
  if Path(analysis_txt_path).exists(): os.remove(analysis_txt_path)
  #Delete analysis.txt again in case of program termination
  if keep == False and logs == False: atexit.register(clean_on_exit,analysis_txt_path)
  #Load images into NudeNet for analysis
  with open(all_images_txt_path,"r") as all_images_txt, open(analysis_txt_path,"w",newline='') as analysis_txt:
#    images = [line.rstrip('\n') for line in all_images_txt]
    image_lines = []
    for row in csv.reader(all_images_txt): image_lines.append(row[0])
    tags =[]
    z = 0
    for image_line in image_lines:
      image_path = re.search(r'[0-9]{7}\.jpg', image_line).group()
      #correcting wrong json output from NudeNet
      if fastmode: json_string = str(detector.detect(image_path, mode='fast')).replace("'",'"')
      else: json_string = str(detector.detect(image_path)).replace("'",'"')
      for entry in json.loads(json_string):
        tags.append(entry['label'])
      tag_line = image_line + ' ' + ' '.join(sorted(tags)) + '\n'
      analysis_txt.write(tag_line)
      if verbose: print(tag_line)
      tags.clear()
      z += 1
      if not verbose: print(current_time() + ' INFO:  Step 2 of 6: Sample images analysed: ' + str(z) + ' out of ' + str(len(image_lines)),end='\r')
  print(current_time() + ' INFO:  Step 2 of 6: Finished analysing ' + str(z) + ' images with NudeNet')
  
  #images_dir can be deleted if analysation has been finished
  if keep == False: atexit.register(clean_on_exit,images_dir)
  os.chdir(startdir)


if 3 in code_sections: #on/off switch for code
  print('\n' + current_time() + ' INFO:  Step 3 of 6: Finding selected tags ...')

#Create clean folders/files
  recreate(matched_images_txt_path)
  os.chdir(tmpdir)

  match_count = 0
  with open(analysis_txt_path,"r") as analysis_txt, open(matched_images_txt_path,"w") as matched_images_txt:
    for line in analysis_txt:
      foundtags = False
      for check in wanted:
        if check in line:
          foundtags = True
          for uncheck in unwanted:
            #string has to be nonempty, otherwise "empty in nonempty" will always uncheck
            if uncheck: 
              if uncheck in line:
                foundtags = False
                break #one unwanted tag is enough to exclude the whole line
      if foundtags:
        matched_images_txt.write(line)
        match_count +=1
  print(current_time() + ' INFO:  Step 3 of 6: Found selected tags in ' + str(match_count) + ' images.')
  if match_count == 0:
    os.chdir(startdir)
    with open(startdir.joinpath(video_name.stem + addtofilename + '_nomatch.txt'),"w") as info_txt:
      infotext = current_time() + ' INFO:  Step 3 of 6: No matches found :('
      info_txt.write(infotext)
    sys.exit(infotext)
  os.chdir(startdir)


if 4 in code_sections: #on/off switch for code
  print('\n' + current_time() + ' INFO:  Step 4 of 6: Finding cut positions ...')  

#Create clean folders/files
  recreate(cuts_txt_path)
  os.chdir(tmpdir)

  with open(matched_images_txt_path,"r") as matched_images_txt, open(cuts_txt_path,"w") as cuts_txt:
    for line in matched_images_txt:
      imagelist.append(int(round(float(re.match(r'[0-9\.]+', line).group()))))
      lines.append(line)
 
    found_segment_start = False
    for i in range(0,len(imagelist)):
# variables
      last_element = len(imagelist) - 1
      #avoid using elements not existent in list
      if i == 0: gap_to_prev_match = 0
      else: gap_to_prev_match = imagelist[i] - imagelist[i - 1]
      if i == last_element: gap_to_next_match = 0
      else: gap_to_next_match = imagelist[i + 1] - imagelist[i]
      segment_start = imagelist[i] - segment_extension
      segment_end = imagelist[i] + segment_extension
      #different parts making up a cut inbetween sample images, where the resulting segments need to be split apart
      #extension and a safety margin to make up for ffmpeg jumping to the closest keyframe during a cut on both ends
      #this will avoid segment overlaps. default keyframe interval is set to 1.
      cut_duration = segment_gap + 2 * segment_extension + 2 * keyframe_interval

# case for finding the start of a segment
      #if first element has matches in reach become beginning
      #or if previous match is too far away
      if (i == 0 and gap_to_next_match <= cut_duration) or (gap_to_prev_match > cut_duration):
        #save beginning timestamp
        if segment_start >= 0: b = segment_start #segment_extension only if timestamp doesn't become negative
        else: 
          b = 0 #otherwise use 0 as a beginning
        found_segment_start = True
# case for finding the end of a segment and finalizing it
      #if next match is too far away
      #if last element while previous match is close
      if (gap_to_next_match > cut_duration) or (i == last_element and gap_to_prev_match <= cut_duration):
        #save ending timestamp, only include segment_extension if timestamp doesn't exceed file duration
        if duration > segment_end: e = segment_end
        else: e = duration
        if found_segment_start:
          segment_duration = e - b
          #finalize segment
          #only finalize if the result would have a positive duration
          #only finalize segment if long enough
          if (segment_duration > 0) and (segment_duration >= min_segment_duration):
            beginnings.append(b)
            endings.append(e)

    # else go to next sample without doing anything

    if verbose: print('Image list: ' + str(imagelist) + '\nBeginnings: ' + str(beginnings) + '\nEndings: ' + str(endings))

# Write results to file    
    for i in range(0, len(beginnings)):
      cuts_txt.write(str(beginnings[i]) + ' ' + str(endings[i]) + ' ' + str(datetime.timedelta(0, beginnings[i])) + ' ' + str(datetime.timedelta(0, endings[i])) + '\n')

  os.chdir(startdir)

# Abort if no segments are found
  if len(endings) < 1:
    infotext = current_time() + ' INFO:  Step 4 of 6: No segments found. Nothing to cut... :('
    with open(startdir.joinpath(video_name.stem + addtofilename + '_nosegments.txt'),"w") as info_txt:
      info_txt.write(infotext)
    sys.exit(infotext)
# Abort if first segment is identical to the whole source video
  elif beginnings[0] == 0 and endings[0] >= duration - 1:
    infotext = current_time() + ' INFO:  Step 4 of 6: Found segment is identical to the source video. Nothing to cut... :)'
    #Only copy if video container of source and destination are the same, otherwise convert
    if os.path.splitext(video_name)[1] == '.' + str(file_ext):
      with open(startdir.joinpath(video_name.stem + addtofilename + '_identical.txt'),"w") as info_txt:
        info_txt.write(infotext)
      sys.exit(infotext)
# In case a copy of the original is wanted, this line could be uncommented:
#      shutil.copy2(video_path,os.path.splitext(video_path)[0] + addtofilename + os.path.splitext(video_path)[1])
    else: 
      print('Converting video from ' + os.path.splitext(video_path)[1] + ' to ' + str(file_ext) + '...',end='\r')
      os.system('ffmpeg -i "' + str(video_path) + str(os.path.splitext(video_path)[0] + addtofilename + '.' + str(file_ext)))
    sys.exit('Finished converting the video from ' + os.path.splitext(video_path)[1] + ' to ' + str(file_ext))
  else:
    print(current_time() + ' INFO:  Step 4 of 6: Found cut positions resulting in ' + str(len(beginnings)) + ' segments.')

#option to confirm overwriting in ffmpeg
if quiet and confirm_overwrite: ffmpeg_overwrite = ' -y'
if quiet and (not confirm_overwrite): ffmpeg_overwrite = ' -n'
if (not quiet): ffmpeg_overwrite = ''

#option to show ffpmeg output
if verbose: quietffmpeg = ''
else: quietffmpeg = ' -v quiet'

if 5 in code_sections: #on/off switch for code
  print('\n' + current_time() + ' INFO:  Step 5 of 6: Extracting video segments with ffmpeg ...')

#Create clean folders/files
  recreate(segments_txt_path,segments_dir)
  if create_negative: recreate(excluded_segments_txt_path,excluded_segments_dir)

  #read timestamps into a list of lists
  with open(cuts_txt_path,"r") as cuts_txt:
    csv_reader = csv.reader(cuts_txt, delimiter=' ')
    timestamps = list(csv_reader) #[i][0] for beginnings, [i][1] for endings

    #Use ffmpeg to extract segments
    def extract_segments(dir,txt,ts):
      os.chdir(dir)
      with open(txt,"w") as segments_txt:
        if txt == excluded_segments_txt_path: negative_str = ' negative'
        else: negative_str = ''
        for i in range(0,len(ts)):
          ffmpeg_cut_start = int(ts[i][0])
          ffmpeg_cut_end = int(ts[i][1])
          ffmpeg_cut_duration = ffmpeg_cut_end - ffmpeg_cut_start
          segment_path = dir.joinpath(video_name.stem + '_' + str(ts[i][0]).zfill(7) + '-' + str(ts[i][1]).zfill(7) + '.' + str(file_ext))
          ffmpeg_cut_input_options = ffmpeg_overwrite + quietffmpeg + ' -vsync 0 -ss ' + str(ts[i][0]) + ' -i "'
          ffmpeg_cut_output_options = '" -t ' + str(ffmpeg_cut_duration) + ' -c copy ' + '"' + str(segment_path) + '"'
          ffmpeg_cut_cmd = 'ffmpeg' + ' ' + ffmpeg_cut_input_options + str(video_path) + ffmpeg_cut_output_options
          #Write output filenames into file for ffmpeg -f concat
          segments_txt.write("file 'file:" + str(dir.joinpath(segment_path.stem)).replace('\\', '/') + "'\n")
          if verbose: print(ffmpeg_cut_cmd)
          os.system(ffmpeg_cut_cmd)
          if keep_filedate: os.utime(segment_path,ns=(modification_time, modification_time))
          if not verbose: print(current_time() + ' INFO:  Step 5 of 6: Extracting' + negative_str + ' segments: ' + str(i+1) + ' out of ' + str(len(ts)),end='\r')
        print(current_time() + ' INFO:  Step 5 of 6: Finished extracting ' + str(len(ts)) + negative_str + ' video segments.')
        if txt == excluded_segments_txt_path: os.chdir(segments_dir)

    #Makes a new timestamp table with all non-selected parts
    def inverse_timestamps(ts):
      inverse_timestamps = []
      found_inverse = 0
      for i in range(0,len(ts)):
        if (i == 0) and (int(ts[0][0]) != 0):
          inverse_timestamps.append([0,int(ts[0][0])])
          found_inverse +=1
        if (i == len(ts) - 1) and (int(ts[-1][1]) != duration):
          inverse_timestamps.append([int(ts[-1][1]),duration])
          found_inverse +=1
        if  i < len(ts) - 1:
          inverse_timestamps.append([int(ts[i][1]),int(ts[i+1][0])])
          found_inverse +=1
      if found_inverse < 1: return False
      else: return inverse_timestamps

    extract_segments(segments_dir,segments_txt_path,timestamps)
    if create_negative and inverse_timestamps(timestamps): extract_segments(excluded_segments_dir,excluded_segments_txt_path,inverse_timestamps(timestamps))

  os.chdir(startdir)

  

if 6 in code_sections: #on/off switch for code
  print('\n' + current_time() + ' INFO:  Step 6 of 6: Creating final video with ffmpeg ...')

#Create clean folders/files
  recreate(segments_txt_path)
  if create_negative: recreate(excluded_segments_txt_path)

#Recreate txt in case the user deleted, added or reordered files in the segment folder
  def scan_segments(dir,txt):
    os.chdir(dir)
    with open(txt,"w",newline='') as segments_txt:
      file_list = [f for f in os.listdir(dir) if re.search(r'.*\.' + str(file_ext), f)]
      i = 0
      for file in file_list:
        segments_txt.write("file 'file:" + str(dir.joinpath(file)).replace('\\', '/') + "'\n")
        if verbose: print(file)
        i +=1
    return file_list, i

  segment_files, segments_count = scan_segments(segments_dir,segments_txt_path)
  if create_negative: excluded_segment_files, excluded_segments_count = scan_segments(excluded_segments_dir,excluded_segments_txt_path)

#Use ffmpeg to concatenate
  def concat_segments(dir,txt,file_list,count):
    os.chdir(dir)
    if dir == excluded_segments_dir: negative_str = '_negative'
    else: negative_str = ''
    ffmpeg_concat_destpath = Path(os.path.splitext(video_path)[0] + addtofilename + negative_str + '.' + str(file_ext))
    ffmpeg_concat_options = quietffmpeg + ffmpeg_overwrite + ' -vsync 0 -safe 0 -f concat -i "' + txt.replace('\\', '/') + '" -c copy'
    ffmpeg_concat_cmd = 'ffmpeg' + ' ' + ffmpeg_concat_options + ' ' + '"' + str(ffmpeg_concat_destpath) + '"'
    #Don't use ffmpeg concat if it is only a single segment with the same video cotainer
    if (count == 1) and (os.path.splitext(video_name)[1] == '.' + str(file_ext)):
      shutil.move(os.path.join(dir,Path(file_list[0])),ffmpeg_concat_destpath)
    else:
      if verbose: print(ffmpeg_concat_cmd)
      os.system(ffmpeg_concat_cmd)
    if keep_filedate: os.utime(ffmpeg_concat_destpath,ns=(modification_time, modification_time))

  concat_segments(segments_dir,segments_txt_path,segment_files,segments_count)
  if create_negative:
    if excluded_segments_count > 0:
      concat_segments(excluded_segments_dir,excluded_segments_txt_path,excluded_segment_files,excluded_segments_count)
  print(current_time() + ' INFO:  Step 6 of 6: Finished creating final video with ffmpeg.')

#segments_dir can be deleted if final video has been made
  if keep == False: 
    atexit.register(clean_on_exit,segments_dir)
    if create_negative: atexit.register(clean_on_exit,excluded_segments_dir)

  os.chdir(startdir)

popdir() # Return to initial directory
print('--- Finished ---\n')

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
from pathlib import Path
from nudenet import NudeDetector
from csv import reader

detector = NudeDetector()

MIN_PYTHON = (3, 7, 6)
if sys.version_info < MIN_PYTHON:
  sys.exit("\nPython %s.%s.%s or later is required.\n" % MIN_PYTHON)

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
parser.add_argument('-g', '--gap', type=int, help='Split segments more than x seconds apart (default: 30)')
parser.add_argument('-d', '--duration', type=int, help='Discard segments shorter than x seconds (default: 10)')
parser.add_argument('-e', '--extension', type=int, help='Extend start and end of segments by x seconds (default: 3)')
parser.add_argument('-b', '--beginning', type=int, help='Skip x seconds of beginning (default: 0)')
parser.add_argument('-f', '--finish', type=int, help='Skip x seconds of finish (default: 0)')
parser.add_argument('-p', '--preset', type=str, help='Name of the config preset to use')
parser.add_argument('-s', '--subset', type=str, help='Subset of preset, eg. site that the model appears on')
parser.add_argument('-w', '--wanted', type=str, help='Tags being used, seperated by comma')
parser.add_argument('-u', '--unwanted', type=str, help='Tags being specifically excluded, seperated by comma')
parser.add_argument('-q', '--quick', default=False, action='store_true', help='Lower needed certainty for matches from 0.6 to 0.5 (default: False)')
parser.add_argument('-l', '--logs', default=False, action='store_true', help='Keep the logs after every step (default: False)')
parser.add_argument('-k', '--keep', default=False, action='store_true', help='Keep all temporary files (default: False)')
parser.add_argument('-v', '--verbose', default=False, action='store_true', help='Output working information (default: False)')
parser.add_argument('-y', '--overwrite', default=False, action='store_true', help='Confirm all questions to overwrite (batch process)')
parser.add_argument('-n', '--negative', default=False, action='store_true', help='Create compililation of all excluded segments too')
parser.add_argument('-1', '--images', action='append_const', dest='switches', const=1, help='Only create image samples')
parser.add_argument('-2', '--analyse', action='append_const', dest='switches', const=2, help='Only analyse with NudeNet AI. Requires all_images.txt')
parser.add_argument('-3', '--match', action='append_const', dest='switches', const=3, help='Only find matching tags. Requires analysis.txt')
parser.add_argument('-4', '--timestamps', action='append_const', dest='switches', const=4, help='Only find cut positions. Requires matched_images.txt')
parser.add_argument('-5', '--split', action='append_const', dest='switches', const=5, help='Only extract segments at cut markers. Requires cuts.txt')
parser.add_argument('-6', '--save', action='append_const', dest='switches', const=6, help='Only connect segements and save final result. Requires segments.txt')

args = parser.parse_args()

#Only really use subset when preset given
if args.preset:
  preset = args.preset.lower()
  if args.subset: subset = args.subset.lower()
  else: subset = False
else:
  preset = 'default'
  if args.subset: preset = args.subset.lower()
  else: subset = False
    

video_name = Path(args.file)
fastmode = args.quick
keep = args.keep
logs = args.logs
verbose = args.verbose
create_negative = args.negative

# Create variables in case no --overwrite given
if args.overwrite: overwrite = True #allow overwriting temp folder
else: overwrite = False


# Default wanted is gender neutral, if a particular gender is required it can be entered into the config file per preset
# Other terms can also be set in the config, see https://github.com/Jafea7/RecFilter3 for valid terms
wanted = ['EXPOSED_BREAST', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS', 'EXPOSED_GENITALIA', 'EXPOSED_BELLY']
unwanted = []
file_ext = 'mp4' # In case there's no videoext entry in the config

print('\nINFO:  Input file: ')
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
if args.beginning:
  skip_begin = args.beginning
  commandline['begin'] = args.beginning
else: skip_begin = 0
if args.finish:
  skip_finish = args.finish
  commandline['finish'] = args.finish
else: skip_finish = 0
if args.wanted:
  wanted = args.wanted.split(',')
  commandline['include'] =  args.wanted
if args.unwanted:
  unwanted = args.unwanted.split(',')
  commandline['exclude'] =  args.unwanted


#Load config
config_path = Path(os.path.splitext(sys.argv[0])[0] + '.json')
if config_path.exists() == False:
  print('\nWARN:  No config file \'%s\' found.' % config_path)
else:
  try:
    with open(config_path) as f:
      data = json.load(f)
      config = True
  except Exception as config_error: 
    print('\nERROR:  Config file ' + str(config_path) + ' is invalid. The following error occured: ')
    print(config_error)
    config = False
  if config_path.exists() == False or config == False:
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


if config and preset:
#Check whether a line in the config even exists
  def config_line_exists(key):
  #the following try block on the datatype is necessary to check for existence, 
  #because in the case values are set to 0 it will give back False instead of True
    try:
      if type(data['presets'][i][key]):
        return True
    except:
      return False
  
#Check whether the value hasn't been set already by a higher priority preset
  def write_config_value(key,type):
    if config_line_exists(key):
      if isinstance(data['presets'][i][key],type):
        #Don't overwrite values given via command line
        if (key in commandline) == False:
          #Inherit has to be allowed. Otherwise it prevents a second inherit.
          if ((key in inconfig) == False) or (key == 'inherit') or (key == 'filesuffix'):
            #split up tags to not use up too much space
            if key == ('include' or 'exclude'):
              split_tags = format(data['presets'][i][key]).split(',')
              for tag in split_tags:
                print('Preset: ' + format(data['presets'][i]['name'] + '  ').ljust(max_presetname_len,'-')[:30] + ('>  ' + key + ': ').rjust(15,'-') + tag)
            else:
              print('Preset: ' + format(data['presets'][i]['name'] + '  ').ljust(max_presetname_len,'-')[:30] + ('>  ' + key + ': ').rjust(15,'-') + str(data['presets'][i][key]))
            inconfig.append(key)
            return True
          else: return False
        else: return False
      else: sys.exit('\nERROR:  ' + key + ' in preset ' + data['presets'][i]['name'] + ' needs to be ' + str(type))
    else: return False

#Used variables
  inconfig = []
  inherit = ''
  presets_found = []
  max_presetname_len = 0
  filesuffix_list = []
  list_of_valid_config_keys = ['name','note','inherit','interval','gap','duration','extension','subset','include','exclude','begin','finish','filesuffix','videoext']

#Find longest preset name for formatting the output
  for i in range(0,len(data['presets'])):
    if len(data['presets'][i]['name']) > max_presetname_len:
        max_presetname_len = len(data['presets'][i]['name'])

  print('\nINFO:  Using the following settings:')

#Ouput command line settings
  for i in range(0,len(commandline)):
    print('Preset: ' + 'commandline  '.ljust(max_presetname_len,'-') + ('>  ' + str(list(commandline.items())[i][0]) + ': ').rjust(15,'-') + (str(list(commandline.items())[i][1])))

#Check config keys for typos
  for i in data['presets']:
    for j in i:
      if j in list_of_valid_config_keys: pass
      else: sys.exit('\nERROR:  Config key ' + j + ' is invalid. Check for typos.')

#Loop through all the config presets
  i = 0
  while i < len(data['presets']):
    justinherited = False #reset re-loop trigger
    #skip presets that have already been applied
    if (data['presets'][i]['name'].lower() in presets_found) == False:
      if (data['presets'][i]['name'].lower() == preset) or (data['presets'][i]['name'].lower() == inherit):
        #reset inherit to an empty string once we were able to use it to get into the right preset         
        if data['presets'][i]['name'].lower() == inherit: inherit = ''
        #if subset is used, the subset has to match, otherwise only inherit allows entry
        if (subset == False) or (subset and data['presets'][i]['subset'].lower() == subset):
          if write_config_value('inherit',str):
            inherit = (data['presets'][i]['inherit'])
            justinherited = True #trigger to rerun preset loop
          if write_config_value('interval',int): sample_interval = data['presets'][i]['interval']
          if write_config_value('gap',int): segment_gap = data['presets'][i]['gap']
          if write_config_value('duration',int): min_segment_duration = data['presets'][i]['duration']
          if write_config_value('extension',int): segment_extension = data['presets'][i]['extension']
          if write_config_value('include',str): wanted = data['presets'][i]['include'].split(',')
          if write_config_value('exclude',str): unwanted = data['presets'][i]['exclude'].split(',')
          if write_config_value('begin',int): skip_begin = data['presets'][i]['begin']
          if write_config_value('finish',int): skip_finish = data['presets'][i]['finish']
          if write_config_value('filesuffix',str): filesuffix_list.append(data['presets'][i]['filesuffix'])
          if write_config_value('videoext',str): file_ext = data['presets'][i]['videoext']
          #note down used presets, so we can skip them
          presets_found.append(data['presets'][i]['name'].lower())
          #stop the loop once default was applied as a last possible inheritance
          if 'default' in presets_found: break
    #if it was the last preset and no inheritance has been set, inherit the default preset
    if (i >= len(data['presets']) - 1) and inherit == '':
      inherit = 'default'
      justinherited = True
    #If a preset inherits look through all presets again
    if justinherited: i = 0
    else: i+=1

  if preset.lower() not in presets_found:
    print('\nINFO:  Preset \'' + preset + '\' not found, using defaults.')
    print("\nThere might be a typo in your --preset argument.\nAre you sure you want to continue with default arguments?")
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

#Check tags for typos
valid_tags = ["EXPOSED_ANUS","EXPOSED_ARMPITS","COVERED_BELLY","EXPOSED_BELLY","COVERED_BUTTOCKS","EXPOSED_BUTTOCKS","FACE_F","FACE_M","COVERED_FEET","EXPOSED_FEET","COVERED_BREAST_F","EXPOSED_BREAST_F","COVERED_GENITALIA_F","EXPOSED_GENITALIA_F","EXPOSED_BREAST_M","EXPOSED_GENITALIA_M","FACE","EXPOSED_BREAST","EXPOSED_GENITALIA"]

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

# Change to video container directory
pushdir(Path(video_path).parent) 

#Finding video duration
ffprobe_out = int( float( subprocess.check_output('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -i "' + str(video_path) + '"', shell=True).decode() ) )
duration = ffprobe_out - skip_finish
if verbose:
  print('\nINFO:  Duration of input video: ')
  print(str(duration) + ' seconds')

# Activation and deactivation of whole program sections
try:
  if len(args.switches) > 0:
    code_sections = []
    #prevent user from skipping inbetween steps when naming more than one program section
    args.switches.sort()
    for i in range(args.switches[0], args.switches[-1] + 1):
      code_sections.append(i)
    print('\nINFO:  Execution restricted by user:')
    print('Only the following program steps will be processed:')
    if 1 in code_sections: print('- Step 1 of 6: Creation of image samples')
    if 2 in code_sections: print('- Step 2 of 6: Analysis through NudeNet AI')
    if 3 in code_sections: print('- Step 3 of 6: Find tags')
    if 4 in code_sections: print('- Step 4 of 6: Find cut markers')
    if 5 in code_sections: print('- Step 5 of 6: Extract segments at cut markers')
    if 6 in code_sections: print('- Step 6 of 6: Connect segments and save final result')
    logs = True
    print('\nINFO:  Option --logs was set to true automatically:')
    print('Text files will be kept as input for further processing.')
#if the user didn't specify any sections run all sections
except: code_sections = [1,2,3,4,5,6]

# Creation of temporary folders
print('\nINFO:  Creating temporary directory ...')
if Path(tmpdir).exists():
    print('WARN:  The following temporary folder will be overwritten:')
    print(os.path.abspath(tmpdir))
    print('\nAre you sure you want to potentially overwrite previous results?')
    print('[y/n] ')
    stop = 0
    while stop == 0:
      if overwrite == True:
        answer = 'y'
      else:
        answer = str( input().lower().strip() )
      if answer == 'y':
        stop = 1
      elif answer == 'n':
        sys.exit('Creation of the temporary directory failed')
        stop = 1
      else: print("Please enter y or n.")
else:
  try:
    os.mkdir(tmpdir)
    print('INFO:  Created temporary directory')
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
  if verbose and fastmode: print('INFO:  Step 1 of 6: Fast mode activated:')
  if verbose and fastmode: print('INFO:  Step 1 of 6: Images will be resized to a max side length of ' + str(max_side_length) )
  print('INFO:  Step 1 of 6: Creating sample images ...')

#Create clean folders/files
  recreate(all_images_txt_path,images_dir)
  os.chdir(images_dir)

#Create images with ffmpeg
  with open(all_images_txt_path,"w", newline='') as all_images_txt:
    image_ffmpeg_filenames = '%07d.jpg'
    image_ffmpeg_inputpath = '-i "'+ str(video_path) + '"'
    if fastmode: image_ffmpeg_resize = "',scale=\'" + str(max_side_length) + ":" + str(max_side_length) + ":force_original_aspect_ratio=decrease\'"
    else: image_ffmpeg_resize = "',scale=\'" + str(max_side_length) + ":" + str(max_side_length) + ":force_original_aspect_ratio=decrease\'"
    image_ffmpeg_inputoptions = ' -v quiet -y -skip_frame nokey -copyts -start_at_zero -ss ' + str(skip_begin)
    image_ffmpeg_outputoptions = '-t ' + str(duration) + ' -vf "fps=1,select=\'not(mod(t,' + str(sample_interval) + '))' + image_ffmpeg_resize + '"' + ' -vsync 0 -an -qmin 1 -q:v 1' + ' ' + image_ffmpeg_filenames
    image_ffmpeg_cmd = 'ffmpeg' + ' ' + image_ffmpeg_inputoptions + ' ' + image_ffmpeg_inputpath + ' ' + image_ffmpeg_outputoptions
    if verbose: print(image_ffmpeg_cmd)
    os.system(image_ffmpeg_cmd)
    image_csv = csv.writer(all_images_txt)
    file_list = [f for f in os.listdir(images_dir) if re.search(r'[0-9]{7}.jpg', f)]
    image_count = 0
    for file in file_list:
      image_csv.writerow([file])
      if verbose: print(file)
      image_count +=1
  print('INFO:  Step 1 of 6: Finished creating ' + str(image_count) + ' sample images.\n')    
  os.chdir(startdir)


if 2 in code_sections: #on/off switch for code
  if verbose and fastmode: print('INFO:  Step 2 of 6: Fast mode for NudeNet was activated')
  print('INFO:  Step 2 of 6: Analysing images with NudeNet ...')

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
    images = []
    for row in csv.reader(all_images_txt): images.append(row[0])
    tags =[]
    z = 0
    for image in images:
      #correcting wrong json output from NudeNet
      if fastmode: json_string = str(detector.detect(image, mode='fast')).replace("'",'"')
      else: json_string = str(detector.detect(image)).replace("'",'"')
      for entry in json.loads(json_string):
        tags.append(entry['label'])
      tag_line = [image] + sorted(tags)
      csv.writer(analysis_txt,delimiter=' ').writerow(tag_line)
      if verbose: print(' '.join(tag_line))
      tags.clear()
      z += 1
      if not verbose: print('INFO:  Step 2 of 6: Sample images analysed: ' + str(z) + ' out of ' + str(len(images)),end='\r')
  print('INFO:  Step 2 of 6: Finished analyzing ' + str(z) + ' images with NudeNet')
  
  #images_dir can be deleted if analyzation has been finished
  if keep == False: atexit.register(clean_on_exit,images_dir)
  os.chdir(startdir)


if 3 in code_sections: #on/off switch for code
  print('\nINFO:  Step 3 of 6: Finding selected tags ...')

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
  print('INFO:  Step 3 of 6: Found selected tags in ' + str(match_count) + ' images.')
  if match_count == 0:
    os.chdir(startdir)
    with open(Path(video_path.stem + addtofilename + '.txt'),"w") as info_txt:
      infotext = 'INFO:  Step 3 of 6: No matches found :('
      info_txt.write(infotext)
    sys.exit(infotext)
  os.chdir(startdir)


if 4 in code_sections: #on/off switch for code
  print('\nINFO:  Step 4 of 6: Finding cut positions ...')  

#Create clean folders/files
  recreate(cuts_txt_path)
  os.chdir(tmpdir)

  with open(matched_images_txt_path,"r") as matched_images_txt, open(cuts_txt_path,"w") as cuts_txt:
    for line in matched_images_txt:
      match = re.search(r'\d\d\d\d\d\d\d', line)
      x = int(match.group())
      imagelist.append(x)
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
    infotext = 'INFO:  Step 4 of 6: No segments found. Nothing to cut... :('
    with open(Path(video_path.stem + addtofilename + '_nomatch.txt'),"w") as info_txt:
      info_txt.write(infotext)
    sys.exit(infotext)
# Abort if first segment is identical to the whole source video
  elif beginnings[0] == 0 and endings[0] >= duration - 1:
    print('INFO:  Step 4 of 6: Found segment is identical to the source video. Nothing to cut... :)')
    #Only copy if video container of source and destination are the same, otherwise convert
    if os.path.splitext(video_name)[1] == '.' + str(file_ext):
      with open(Path(video_path.stem + addtofilename + '_identical.txt'),"w") as info_txt:
        info_txt.write(infotext)
      sys.exit()
# In case a copy of the original is wanted, this line could be uncommented:
#      shutil.copy2(video_path,os.path.splitext(video_path)[0] + addtofilename + os.path.splitext(video_path)[1])
    else: 
      print('Converting video from ' + os.path.splitext(video_path)[1] + ' to ' + str(file_ext) + '...',end='\r')
      os.system('ffmpeg -i "' + str(video_path) + str(os.path.splitext(video_path)[0] + addtofilename + '.' + str(file_ext)))
    sys.exit('Finished converting the video from ' + os.path.splitext(video_path)[1] + ' to ' + str(file_ext))
  else:
    print('INFO:  Step 4 of 6: Found cut positions resulting in ' + str(len(beginnings)) + ' segments.')


#option to confirm overwriting in ffmpeg
if args.overwrite == True:
  ffmpeg_overwrite = ' -y'
else: ffmpeg_overwrite = ''

#option to show ffpmeg output
if verbose: quietffmpeg = ''
else: quietffmpeg = ' -v quiet'

if 5 in code_sections: #on/off switch for code
  print('\nINFO:  Step 5 of 6: Extracting video segments with ffmpeg ...')

#Create clean folders/files
  recreate(segments_txt_path,segments_dir)
  if create_negative: recreate(excluded_segments_txt_path,excluded_segments_dir)

  #read timestamps into a list of lists
  with open(cuts_txt_path,"r") as cuts_txt:
    csv_reader = reader(cuts_txt, delimiter=' ')
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
          segment_name = str(video_name.stem) + '_' + str(ts[i][0]).zfill(7) + '-' + str(ts[i][1]).zfill(7) + '.' + str(file_ext)
          ffmpeg_cut_input_options = ffmpeg_overwrite + quietffmpeg + ' -vsync 0 -ss ' + str(ts[i][0]) + ' -i "'
          ffmpeg_cut_output_options = '" -t ' + str(ffmpeg_cut_duration) + ' -c copy ' + segment_name
          ffmpeg_cut_cmd = 'ffmpeg' + ' ' + ffmpeg_cut_input_options + str(video_path) + ffmpeg_cut_output_options
          #Write output filenames into file for ffmpeg -f concat
          segments_txt.write("file 'file:" + str(dir.joinpath(segment_name)).replace('\\', '/') + "'\n")
          if verbose: print(ffmpeg_cut_cmd)
          os.system(ffmpeg_cut_cmd)
          if not verbose: print('INFO:  Step 5 of 6: Extracting' + negative_str + ' segments: ' + str(i+1) + ' out of ' + str(len(ts)),end='\r')
        print('INFO:  Step 5 of 6: Finished extracting ' + str(len(ts)) + negative_str + ' video segments.')
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
  print('\nINFO:  Step 6 of 6: Creating final video with ffmpeg ...')

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
    ffmpeg_concat_destname = os.path.splitext(video_path)[0] + addtofilename + negative_str + '.' + str(file_ext)
    ffmpeg_concat_options = quietffmpeg + ffmpeg_overwrite + ' -vsync 0 -safe 0 -f concat -i "' + txt.replace('\\', '/') + '" -c copy'
    ffmpeg_concat_cmd = 'ffmpeg' + ' ' + ffmpeg_concat_options + ' ' + '"' + ffmpeg_concat_destname + '"'
    #Don't use ffmpeg concat if it is only a single segment with the same video cotainer
    if (count == 1) and (os.path.splitext(video_name)[1] == '.' + str(file_ext)):
      shutil.move(os.path.join(dir,Path(file_list[0])),Path(ffmpeg_concat_destname))
    else:
      if verbose: print(ffmpeg_concat_cmd)
      os.system(ffmpeg_concat_cmd)

  concat_segments(segments_dir,segments_txt_path,segment_files,segments_count)
  if create_negative:
    if excluded_segments_count > 0:
      concat_segments(excluded_segments_dir,excluded_segments_txt_path,excluded_segment_files,excluded_segments_count)
  print('INFO:  Step 6 of 6: Finished creating final video with ffmpeg.')

#segments_dir can be deleted if final video has been made
  if keep == False: 
    atexit.register(clean_on_exit,segments_dir)
    if create_negative: atexit.register(clean_on_exit,excluded_segments_dir)

  os.chdir(startdir)

popdir() # Return to initial directory
print('--- Finished ---\n')

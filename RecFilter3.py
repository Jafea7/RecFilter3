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

def exit_handler(signum, frame):
  if video_path is not None: # Haven't got this then have only read config
    if tmpdir is not None:   # If we got this then we're in the video or tmpdir
      if Path(os.getcwd()).stem == tmpdir: # If in the tmpdir then retrace a dir
        popdir()
      # Launch tmpdir deletion as separate process, RecFilter locks a file which prevents deletion under certain circumstances
      subprocess.Popen(["python","-c","import shutil; import time; time.sleep(1); shutil.rmtree(\"" + tmpdir + "\", ignore_errors=True)"])
  sys.exit(0)

signal.signal(signal.SIGINT, exit_handler) # Handle Ctrl-C

print('\n--- RecFilter3 ---')
parser = argparse.ArgumentParser(prog='RecFilter', description='RecFilter: Remove SFW sections of videos')
parser.add_argument('file', type=str, help='Video file to process')
parser.add_argument('-i', '--interval', type=int, default=5, help='Interval between image samples (default: 5)')
parser.add_argument('-g', '--gap', type=int, default=30, help='Split segments more than x seconds apart (default: 30)')
parser.add_argument('-d', '--duration', type=int, default=10, help='Discard segments shorter than x seconds (default: 10)')
parser.add_argument('-e', '--extension', type=int, default=3, help='Extend start and end of segments by x seconds (default: 3)')
parser.add_argument('-b', '--beginning', type=int, default=0, help='Skip x seconds of beginning (default: 0)')
parser.add_argument('-f', '--finish', type=int, default=0, help='Skip x seconds of finish (default: 0)')
parser.add_argument('-p', '--preset', type=str, help='Name of the config preset to use')
parser.add_argument('-s', '--subset', type=str, help='Subset of preset, eg. site that the model appears on')
parser.add_argument('-q', '--quick', default=False, action='store_true', help='Lower needed certainty for matches from 0.6 to 0.5 (default: False)')
parser.add_argument('-l', '--logs', action='store_true', help='Keep the logs after every step (default: False)')
parser.add_argument('-k', '--keep', action='store_true', help='Keep all temporary files (default: False)')
parser.add_argument('-v', '--verbose', action='store_true', help='Output working information (default: False)')
parser.add_argument('-y', '--overwrite', default=False, action='store_true', help='Confirm all questions to overwrite (batch process)')
parser.add_argument('-1', '--images', action='append_const', dest='switches', const=1, help='Only create image samples')
parser.add_argument('-2', '--analyse', action='append_const', dest='switches', const=2, help='Only analyse with NudeNet AI. Requires all_images.txt')
parser.add_argument('-3', '--match', action='append_const', dest='switches', const=3, help='Only find matching tags. Requires analysis.txt')
parser.add_argument('-4', '--timestamps', action='append_const', dest='switches', const=4, help='Only find cut positions. Requires matched_images.txt')
parser.add_argument('-5', '--split', action='append_const', dest='switches', const=5, help='Only extract segments at cut markers. Requires cuts.txt')
parser.add_argument('-6', '--save', action='append_const', dest='switches', const=6, help='Only connect segements and save final result. Requires segments.txt')

args = parser.parse_args()

if ((args.site is not None) and
    (args.preset is None)):
  parser.error('The --subset argument requires a --preset argument')

video_name = Path(args.file)
sample_interval = args.interval
min_segment_duration = args.duration
segment_gap = args.gap
segment_extension = args.extension
skip_begin = args.beginning
skip_finish = args.finish
if args.preset is not None:
  preset = args.preset.lower()
else:
  preset = None
if args.subset is not None:
  subset = args.subset.lower()
else:
  subset = None
fastmode = args.quick
keep = args.keep
logs = args.logs
verbose = args.verbose

# Create variables in case no --overwrite given
overwrite = False
if args.overwrite == True:
  overwrite = True #allow overwriting temp folder

config_path = Path(os.path.splitext(sys.argv[0])[0] + '.json')
try:
  with open(config_path) as f:
    data = json.load(f)
    config = True
except:
  print('\nINFO:  No config file \'%s\' found.' % config_path)
  config = False

# Default wanted is gender neutral, if a particular gender is required it can be entered into the config file per preset
# Other terms can also be set in the config, see https://github.com/Jafea7/RecFilter3 for valid terms
wanted = ['EXPOSED_BREAST', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS', 'EXPOSED_GENITALIA', 'EXPOSED_BELLY']
unwanted = []
fileext = 'mp4' # In case there's no videoext entry in the config

if config:
  if 'default' in data:
    if str(data['default']) != "":
      wanted = data['default'].split(',')
  if 'videoext' in data:
    if str(data['videoext']) != "":
      fileext = data['videoext']
    else:
      fileext = 'mp4'
  if (preset is not None):
    found = False
    for preset_name in data['presets']:
      if (preset_name['name'].lower() == preset):
        if (((subset is not None) and (preset_name['subset'].lower() == subset)) or
          ((subset is None) and (preset_name['subset'].lower() == ''))):
          if preset_name['interval']: sample_interval = preset_name['interval']
          if preset_name['gap']: segment_gap = preset_name['gap']
          if preset_name['duration']: min_segment_duration = preset_name['duration']
          if preset_name['extension']: segment_extension = preset_name['extension']
          if preset_name['include']: wanted = preset_name['include'].split(',')
          if preset_name['exclude']: unwanted = preset_name['exclude'].split(',')
          if preset_name['begin']: skip_begin = preset_name['begin']
          if preset_name['finish']: skip_finish = preset_name['finish']
          found = True
          break
    if not found:
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

print('\nINFO:  Input file: ')
print(str(video_name))
print('\nINFO:  Running with arguments: ')
print('-i ' + str(sample_interval) + ' -c ' + str(segment_gap) + ' -d ' + str(min_segment_duration)+ ' -e ' + str(segment_extension) + ' -b ' + str(skip_begin) + ' -f ' + str(skip_finish) )
print('\nINFO:  Tags that will be matched: ')
print(str(wanted))
print('\nINFO:  Tags that will be excluded: ')
print(str(unwanted))
if fastmode: print('\nINFO:  NudeNet was set to Fast Mode')

if wanted[0] == 'NONE':
  exit()

imagelist = []
lines = []
beginnings = []
endings = []

i = 0
b = None
e = 0
p = 0
z = 0

video_path = Path(video_name).resolve() # Get the full video path
startdir = Path(video_path).parent
tmpdirnaming = '~' + Path(video_name).stem
tmpdir = Path(startdir).joinpath(tmpdirnaming)
images_dir = Path(tmpdir) / 'images'
segments_dir = Path(tmpdir) / 'segments'

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
    #keep temporary directory if user opted to use a specific section
    keep = True
    print('\nINFO:  Execution restricted by user:')
    print('        ' + 'Only the following program steps will be processed:')
    if 1 in code_sections: print('        ' + '- Step 1 of 6: Creation of image samples')
    if 2 in code_sections: print('        ' + '- Step 2 of 6: Analysis through NudeNet AI')
    if 3 in code_sections: print('        ' + '- Step 3 of 6: Find tags')
    if 4 in code_sections: print('        ' + '- Step 4 of 6: Find cut markers')
    if 5 in code_sections: print('        ' + '- Step 5 of 6: Extract segments at cut markers')
    if 6 in code_sections: print('        ' + '- Step 6 of 6: Connect segments and save final result')
    print('INFO:  Option --keep was set to true automatically:')
    print('        ' + 'Temporary files will be kept for further processing.')
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

# Filenames used
all_images_txt_path = os.path.join(tmpdir, 'all_images.txt')
analysis_txt_path = os.path.join(tmpdir, 'analysis.txt')
matched_images_txt_path = os.path.join(tmpdir, 'matched_images.txt')
cuts_txt_path = os.path.join(tmpdir, 'cuts.txt')
segments_txt_path = os.path.join(segments_dir, 'segments.txt')
addtofilename = '_recfilter-i' + str(sample_interval) + '-c' + str(segment_gap) + '-d' + str(min_segment_duration) + '-e' + str(segment_extension)

if 1 in code_sections: #on/off switch for code
  if fastmode: max_side_length = 800
  else: max_side_length = 1280
  if verbose and fastmode: print('INFO:  Step 1 of 6: Fast mode activated:')
  if verbose and fastmode: print('INFO:  Step 1 of 6: Images will be resized to a max side length of ' + str(max_side_length) )
  print('INFO:  Step 1 of 6: Creating sample images ...')
  #Delete previously created folder to rerun steps
  if Path(images_dir).exists(): shutil.rmtree(images_dir, ignore_errors=True)
  os.mkdir(images_dir)
  os.chdir(images_dir)
  #Delete previously created output to rerun steps
  if Path(all_images_txt_path).exists(): os.remove(all_images_txt_path)
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
  os.chdir(images_dir)
  #Delete previously created output to rerun steps
  if Path(analysis_txt_path).exists(): os.remove(analysis_txt_path)
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
  os.chdir(startdir)

if 3 in code_sections: #on/off switch for code
  print('\nINFO:  Step 3 of 6: Finding selected tags ...')
  os.chdir(tmpdir)
  #delete previously created output to rerun steps
  if Path(matched_images_txt_path).exists(): os.remove(matched_images_txt_path)
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
  os.chdir(tmpdir)
  #delete previously created output to rerun steps
  if Path(cuts_txt_path).exists(): os.remove(cuts_txt_path)
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
      #added time between two samples if they were split apart by 1 second
      cut_duration = segment_gap + 2 * segment_extension + 1
      segment_start = imagelist[i] - segment_extension
      segment_end = imagelist[i] + segment_extension

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
      cuts_txt.write(str(beginnings[i]) + ' ' + str(endings[i]) + '\n')

  os.chdir(startdir)

# Abort if no segments are found
  if len(endings) < 1:
    infotext = 'INFO:  Step 4 of 6: No segments found. Nothing to cut... :('
    with open(Path(video_path.stem + addtofilename + '.txt'),"w") as info_txt:
      info_txt.write(infotext)
    sys.exit(infotext)
# Abort if segment is identical to the source video
  elif beginnings[0] == 0 and endings[-1] >= duration - 1:
    infotext = 'INFO:  Step 4 of 6: Found segment is identical to the source video. Nothing to cut... :)'
    with open(Path(video_path.stem + addtofilename + '.txt'),"w") as info_txt:
      info_txt.write(infotext)
    sys.exit(infotext)
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
  os.chdir(startdir)
  #Delete previously created folder to rerun steps
  if Path(segments_dir).exists(): shutil.rmtree(segments_dir, ignore_errors=True)
  os.mkdir(segments_dir)
  os.chdir(segments_dir)
  if Path(segments_txt_path).exists(): os.remove(segments_txt_path)
  #read timestamps into a list of lists and then use it for ffmpeg
  with open(cuts_txt_path,"r") as cuts_txt, open(segments_txt_path,"w") as segments_txt:
    csv_reader = reader(cuts_txt, delimiter=' ')
    timestamps = list(csv_reader) #[i][0] for beginnings, [i][1] for endings
    for i in range(0,len(timestamps)):
      ffmpeg_cut_start = int(timestamps[i][0])
      ffmpeg_cut_end = int(timestamps[i][1])
      ffmpeg_cut_duration = ffmpeg_cut_end - ffmpeg_cut_start
      segment_name = timestamps[i][0] + '-' + timestamps[i][1] + '.' + str(fileext)
      ffmpeg_cut_input_options = ffmpeg_overwrite + quietffmpeg + ' -vsync 0 -ss ' + str(timestamps[i][0]) + ' -i "'
      ffmpeg_cut_output_options = '" -t ' + str(ffmpeg_cut_duration) + ' -c copy ' + segment_name
      ffmpeg_cut_cmd = 'ffmpeg' + ' ' + ffmpeg_cut_input_options + str(video_path) + ffmpeg_cut_output_options
      #Write output filenames into file for ffmpeg -f concat
      segments_txt.write('file ' + segment_name + '\n')
      if verbose: print(ffmpeg_cut_cmd)
      os.system(ffmpeg_cut_cmd)
      if not verbose: print('INFO:  Step 5 of 6: Extracting segments: ' + str(i+1) + ' out of ' + str(len(timestamps)),end='\r')
  print('INFO:  Step 5 of 6: Finished extracting ' + str(len(timestamps)) + ' video segments.')
  os.chdir(startdir)

if 6 in code_sections: #on/off switch for code
  os.chdir(segments_dir)
  print('\nINFO:  Step 6 of 6: Creating final video with ffmpeg ...')
  ffmpeg_concat_options = quietffmpeg + ffmpeg_overwrite + ' -vsync 0 -safe 0 -f concat -i "' + segments_txt_path + '" -c copy'
  ffmpeg_concat_destname = '"' + os.path.splitext(video_path)[0] + addtofilename + '.' + str(fileext) + '"'
  ffmpeg_concat_cmd = 'ffmpeg' + ' ' + ffmpeg_concat_options + ' ' + ffmpeg_concat_destname
  if verbose: print(ffmpeg_concat_cmd)
  os.system(ffmpeg_concat_cmd)
  print('INFO:  Step 6 of 6: Finished creating final video with ffmpeg.')
  os.chdir(startdir)

#popdir() # Return to temporary directory parent
if (not keep) and (not logs): # Delete the temporary directory if no -keep
  print('\nINFO:  Deleting temporary files')
  shutil.rmtree(tmpdir, ignore_errors=True)
elif (not keep) and logs:
  print('\nINFO:  Keeping logs, deleting images and segments')
  shutil.rmtree(images_dir, ignore_errors=True)
  shutil.rmtree(segments_dir, ignore_errors=True)
popdir() # Return to initial directory
print('--- Finished ---\n')

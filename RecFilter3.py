#!/usr/bin/python
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from nudenet import NudeDetector
from csv import reader

detector = NudeDetector()

#MIN_PYTHON = (3, 7, 9)
#if sys.version_info < MIN_PYTHON:
#    sys.exit("\nPython %s.%s.%s or later is required.\n" % MIN_PYTHON)

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

print('\n--- RecFilter2 ---')
parser = argparse.ArgumentParser(prog='RecFilter', description='RecFilter: Remove SFW sections of videos')
parser.add_argument('file', type=str, help='Video file to process')
parser.add_argument('-i', '--interval', type=int, default=5, help='Interval between image samples (default: 20)')
parser.add_argument('-c', '--cut', type=int, default=30, help='Trigger a cut when x seconds without match (default: 30)')
parser.add_argument('-d', '--duration', type=int, default=10, help='Minimum duration of segments (default: 20)')
parser.add_argument('-e', '--extension', type=int, default=3, help='Extend start and end of segments by x seconds (default: 5)')
parser.add_argument('-b', '--beginning', type=int, default=0, help='Skip x seconds of beginning (default: 1)')
parser.add_argument('-f', '--finish', type=int, default=0, help='Skip x seconds of finish (default: 0)')
parser.add_argument('-m', '--model', type=str, help='Model name for config preset')
parser.add_argument('-s', '--site', type=str, help='Site that the model appears on')
parser.add_argument('-k', '--keep', action='store_true', help='Keep temporary working files (default: False)')
parser.add_argument('-v', '--verbose', action='store_true', help='Output working information (default: False)')
parser.add_argument('-y', '--overwrite', default=False, action='store_true', help='Confirm all questions to overwrite (batch process)')
parser.add_argument('-1', '--images', action='append_const', dest='switches', const=1, help='Only create image samples')
parser.add_argument('-2', '--analyse', action='append_const', dest='switches', const=2, help='Only analyse with AI')
parser.add_argument('-3', '--match', action='append_const', dest='switches', const=3, help='Only find matching tags')
parser.add_argument('-4', '--timestamps', action='append_const', dest='switches', const=4, help='Only find cut positions')
parser.add_argument('-5', '--split', action='append_const', dest='switches', const=5, help='Only split at cut markers')
parser.add_argument('-6', '--save', action='append_const', dest='switches', const=6, help='Only connect segements and save final result')

args = parser.parse_args()
if ((args.site is not None) and
    (args.model is None)):
  parser.error('The --site argument requires a --model argument')

video_name = args.file
sample_interval = args.interval
min_segment_duration = args.duration
cut_trigger = args.cut
segment_extension = args.extension
skip_begin = args.beginning
skip_finish = args.finish
if args.model is not None:
  model = args.model.lower()
else:
  model = None
if args.site is not None:
  site = args.site.lower()
else:
  site = None
keep = args.keep
verbose = args.verbose

print('\nINFO:  Input file: ')
print(str(video_name))
print('\nINFO:  Running with arguments: ')
print('-i ' + str(sample_interval) + ' -c ' + str(cut_trigger) + ' -d ' + str(min_segment_duration)+ ' -e ' + str(segment_extension) + ' -b ' + str(skip_begin) + ' -f ' + str(skip_finish) )

# Create variables in case no --overwrite given
overwrite = False
if args.overwrite == True:
  overwrite = True #allow overwriting temp folder

config_path = os.path.abspath(sys.argv[0]).rsplit('.', 1)[0] + '.json'
try:
  with open(config_path) as f:
    data = json.load(f)
    config = True
except:
  print('\nINFO:  No config file \'%s\' found.' % config_path)
  config = False

# Default checkinglist is gender neutral, if a particular gender is required it can be entered into the config file per model
# Other terms can also be set in the config, see https://github.com/Jafea7/RecFilter2 for valid terms
checkinglist = ['EXPOSED_BREAST', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS', 'EXPOSED_GENITALIA', 'EXPOSED_BELLY']
fileext = 'mp4' # In case there's no videoext entry in the config

if config:
  if 'default' in data:
    if str(data['default']) != "":
      checkinglist = data['default'].split(',')
  if 'videoext' in data:
    if str(data['videoext']) != "":
      fileext = data['videoext']
    else:
      fileext = 'mp4'
  if (model is not None):
    found = False
    for cammodel in data['models']:
      if (cammodel['name'].lower() == model):
        if (((site is not None) and (cammodel['site'].lower() == site)) or
          ((site is None) and (cammodel['site'].lower() == ''))):
          frame_duration = cammodel['interval']
          frame_extension = cammodel['extension']
          checkinglist = cammodel['search'].split(',')
          skip_begin = cammodel['begin']
          skip_finish = cammodel['finish']
          found = True
          break
    if not found:
      print('\nINFO:  \'' + model + '\' not found, using defaults.')

print('\nINFO:  Tags that will be matched: ')
print(str(checkinglist))

if checkinglist[0] == 'NONE':
  exit()

imagelist = []
lines = []
beginnings = []
endings = []

i = 0
b = 0
e = 0
p = 0
z = 0

video_path = os.path.abspath(video_name) # Get the full video path
startdir = Path(video_path).parent
tmpdirnaming = '~' + Path(video_name).stem
tmpdir = os.path.join(Path(startdir, tmpdirnaming))
images_dir = os.path.join(tmpdir, 'images')
segments_dir = os.path.join(tmpdir, 'segments')

# Change to video container directory
pushdir(Path(video_path).parent) 

#Finding video duration
ffprobe_out = int( float( subprocess.check_output('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -i "' + video_path + '"', shell=True).decode() ) )
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
    print('\nINFO:  Execution restricted by user.')
    print('        ' + 'Only the following program steps will be processed:')
    if 1 in code_sections: print('        ' + '- Step 1 of 6: Creation of image samples')
    if 2 in code_sections: print('        ' + '- Step 2 of 6: Analysis through NudeNet AI')
    if 3 in code_sections: print('        ' + '- Step 3 of 6: Find tags')
    if 4 in code_sections: print('        ' + '- Step 3 of 6: Find cut markers')
    if 5 in code_sections: print('        ' + '- Step 4 of 6: Split segments at cut markers')
    if 6 in code_sections: print('        ' + '- Step 5 of 6: Connect segments and save final result')
    print('INFO:  Option --keep was set to true automatically.')
    print('        ' + 'Temporary files will be kept for further processing.')
#if the user didn't specify any sections run all sections
except: code_sections = [1,2,3,4,5,6]

# Creation of temporary folders
print('\nINFO:  Creating temporary directory ...')
if Path(tmpdir).exists():
    print('WARN:  The following temporary folder already exists:')
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
        if 1 in code_sections: #on/off switch for code
          try: 
            shutil.rmtree(tmpdir, ignore_errors=True)
            os.mkdir(tmpdir)
          except: sys.exit('Removal and recreation of the tmpdir failed for step 1')
          os.mkdir(images_dir)
          os.mkdir(segments_dir)
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

# Filenames used
all_images_txt_path = os.path.join(tmpdir, 'all_images.txt')
analysis_txt_path = os.path.join(tmpdir, 'analysis.txt')
matched_images_txt_path = os.path.join(tmpdir, 'matched_images.txt')
cuts_txt_path = os.path.join(tmpdir, 'cuts.txt')
segments_txt_path = os.path.join(segments_dir, 'segments.txt')

if 1 in code_sections: #on/off switch for code
  print('\nINFO:  Step 1 of 6: Creating sample images ...')
  #Delete previously created folder to rerun steps
  if Path(images_dir).exists(): shutil.rmtree(images_dir, ignore_errors=True)
  os.mkdir(images_dir)
  os.chdir(images_dir)
  #Delete previously created output to rerun steps
  if Path(all_images_txt_path).exists(): os.remove(all_images_txt_path)
  #Create images with ffmpeg
  with open(all_images_txt_path,"w") as all_images_txt:
   for interval in range(skip_begin, duration, sample_interval):
     image_filename = str(interval).zfill(7) + '.jpg'
     image_inputpath = '-i "'+ video_path + '"'
     image_inputoptions = '-v quiet -y -skip_frame nokey -ss ' + str(interval)
     image_outputoptions = '-vf select="eq(pict_type\\,I),scale=800:-1" -an -q:v 2 -vframes 1' + ' ' + image_filename
     os.system('ffmpeg' + ' ' + image_inputoptions + ' ' + image_inputpath + ' ' + image_outputoptions)
     all_images_txt.write(image_filename + '\n')
     if verbose: print(image_filename)
  os.chdir(startdir)
  print('INFO:  Step 1 of 6: Finished creating sample images')
  
if 2 in code_sections: #on/off switch for code
  print('\nINFO:  Step 2 of 6: Analysing images with NudeNet ...')
  os.chdir(images_dir)
  #Delete previously created output to rerun steps
  if Path(analysis_txt_path).exists(): os.remove(analysis_txt_path)
  #Load images into NudeNet for analysis
  with open(all_images_txt_path,"r") as all_images_txt, open(analysis_txt_path,"w") as analysis_txt:
    images = [line.rstrip('\n') for line in all_images_txt]
    for image in images:
      output  = detector.detect(image)
      y = 0
      stringoutput = ''
      while y < len(output):
        match = re.search(r'\b[A-Z].*?\b', str(output[y]))
        stringoutput += str(match.group()) + '  '
        y +=1
      analysis_txt.write(image + '    ' + stringoutput + '\n')
      if verbose: print(image + ' - ' + stringoutput)
  os.chdir(startdir)
  print('INFO:  Step 2 of 6: Finished analyzing images with NudeNet')

if 3 in code_sections: #on/off switch for code
  print('\nINFO:  Step 3 of 6: Matching user specified tags ...')
  os.chdir(tmpdir)
  #delete previously created output to rerun steps
  if Path(matched_images_txt_path).exists(): os.remove(matched_images_txt_path)
  with open(analysis_txt_path,"r") as analysis_txt, open(matched_images_txt_path,"w") as matched_images_txt:
    for line in analysis_txt:
      for check in checkinglist:
        if check in line:
          matched_images_txt.write(line)
          break
  os.chdir(startdir)
  print('INFO:  Step 3 of 6: Finished matching user specified tags')

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
 
    for i in range(0,len(imagelist)):
# variables
      last_element = len(imagelist) - 1
      #avoid using elements not existent in list
      if i == 0: gap_to_prev_match = 0
      else: gap_to_prev_match = imagelist[i] - imagelist[i - 1]
      if i == last_element: gap_to_next_match = 0
      else: gap_to_next_match = imagelist[i + 1] - imagelist[i]
      #added time between two samples if they were split apart by 1 second
      cut_duration = cut_trigger + 2 * segment_extension + 1
      segment_start = imagelist[i] - segment_extension
      segment_end = imagelist[i] + segment_extension
      
# case for finding the start of a segment
      #if first element has matches in reach become beginning
      #if previous match is too far away
      if (i == 0 and gap_to_next_match <= cut_duration) or (gap_to_prev_match > cut_duration):
        #save beginning timestamp
        if segment_start > 0:
          b = segment_start #only include segment_extension if timestamp doesn't become negative
        else: b = 0

# case for finding the end of a segment and finalizing it
      #if next match is too far away
      #if last element while previous match is close
      if (gap_to_next_match > cut_duration) or (i == last_element and gap_to_prev_match <= cut_duration):
        #save ending timestamp, only include segment_extension if timestamp doesn't exceed file duration
        if duration > segment_end: e = segment_end
        else: e = duration
        segment_duration = e - b
        #finalize segment
      #only finalize if the result would have non negative duration
      #only finalize segment if long enough
        if (segment_duration >= 0) and (segment_duration >= min_segment_duration):
          beginnings.append(b)
          endings.append(e)

      # else go to next sample without doing anything
#      i += 1

    if verbose: print('Image list: ' + str(imagelist) + '\nBeginnings: ' + str(beginnings) + '\nEndings: ' + str(endings))
    for i in range(0, len(beginnings)):
      cuts_txt.write(str(beginnings[i]) + ' ' + str(endings[i]) + '\n')
    os.chdir(startdir)
    print('INFO:  Step 4 of 6: Finished finding cut positions.')

#option to confirm overwriting in ffmpeg
if args.overwrite == True:
  ffmpeg_overwrite = ' -y'
else: ffmpeg_overwrite = ''

#option to show ffpmeg output
if verbose: quietffmpeg = ''
else: quietffmpeg = ' -v quiet'

if 5 in code_sections: #on/off switch for code
  print('\nINFO:  Step 5 of 6: Creating video segments with ffmpeg ...')
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
      ffmpeg_cut_cmd = 'ffmpeg' + ' ' + ffmpeg_cut_input_options + video_path + ffmpeg_cut_output_options
      #Write output filenames into file for ffmpeg -f concat
      segments_txt.write('file ' + segment_name + '\n')
      if verbose: print(ffmpeg_cut_cmd)
      os.system(ffmpeg_cut_cmd)
  os.chdir(startdir)
  print('INFO:  Step 5 of 6: Finished creating video segments with ffmpeg.')

if 6 in code_sections: #on/off switch for code
  os.chdir(segments_dir)
  print('\nINFO:  Step 6 of 6: Creating final video with ffmpeg ...')
  ffmpeg_concat_options = quietffmpeg + ffmpeg_overwrite + ' -vsync 0 -safe 0 -f concat -i "' + segments_txt_path + '" -c copy "'
  ffmpeg_concat_destname = video_path.rsplit('.', 1)[0] + '_recfilter-i' + str(sample_interval) + '-c' + str(cut_trigger) + '-d' + str(min_segment_duration) + '-e' + str(segment_extension) + '.' + str(fileext) + '"'
  ffmpeg_concat_cmd = 'ffmpeg' + ' ' + ffmpeg_concat_options + ffmpeg_concat_destname
  if verbose: print(ffmpeg_concat_cmd)
  os.system(ffmpeg_concat_cmd)
  os.chdir(startdir)
  print('INFO:  Step 6 of 6: Finished creating final video with ffmpeg.')

#popdir() # Return to temporary directory parent
if (not keep): # Delete the temporary directory if no -keep
  print('\nINFO:  Deleting temporary files')
  shutil.rmtree(tmpdir, ignore_errors=True)

popdir() # Return to initial directory
print('--- Finished ---\n')
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
parser.add_argument('-i', '--interval', type=int, default=20, help='Interval between image samples (default: 20)')
parser.add_argument('-c', '--cut', type=int, default=30, help='Trigger a cut when x seconds without match (default: 30)')
parser.add_argument('-d', '--duration', type=int, default=20, help='Minimum duration of segments (default: 20)')
parser.add_argument('-e', '--extension', type=int, default=5, help='Extend start and end of segments by x seconds (default: 5)')
parser.add_argument('-b', '--beginning', type=int, default=1, help='Skip x seconds of beginning (default: 1)')
parser.add_argument('-f', '--finish', type=int, default=0, help='Skip x seconds of finish (default: 0)')
parser.add_argument('-m', '--model', type=str, help='Model name for config preset')
parser.add_argument('-s', '--site', type=str, help='Site that the model appears on')
parser.add_argument('-k', '--keep', action='store_true', help='Keep temporary working files (default: False)')
parser.add_argument('-v', '--verbose', action='store_true', help='Output working information (default: False)')

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
if ((args.site is not None) and
    (model is not None)):
  site = args.site.lower()
else:
  site = None
keep = args.keep
verbose = args.verbose

config_path = os.path.abspath(sys.argv[0]).rsplit('.', 1)[0] + '.json'
try:
  with open(config_path) as f:
    data = json.load(f)
    config = True
except:
  print('INFO: No config file \'%s\' found.' % config_path)
  config = False

# Default checkinglist is gender neutral, if a particular gender is required it can be entered into the config file per model
# Other terms can also be set in the config, see https://github.com/Jafea7/RecFilter2 for valid terms
checkinglist = ['EXPOSED_BREAST', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS', 'EXPOSED_GENITALIA', 'EXPOSED_BELLY']

if config:
  if 'default' in data:
    if str(data['default']) != "":
      checkinglist = data['default'].split(',')
  if 'videoext' in data:
    if str(data['videoext']) != "":
      fileext = data['videoext']
    else:
      fileext = "mp4"
  if ((model is not None)):
    found = False
    for cammodel in data['models']:
      if (site is not None): # site specified, match on site and model
        if ((cammodel['site'].lower() == site) and (cammodel['name'].lower() == model)):
            sample_interval = cammodel['interval']
            cut_trigger = cammodel['cut']
            min_segment_duration = cammodel['duration']
            segment_extension = cammodel['extension']
            checkinglist = cammodel['search'].split(',')
            skip_begin = cammodel['begin']
            skip_finish = cammodel['finish']
            found = True
            break
        else: # site not specified, match on model
          if (cammodel['name'].lower() == model):
            sample_interval = cammodel['interval']
            cut_trigger = cammodel['cut']
            min_segment_duration = cammodel['duration']
            segment_extension = cammodel['extension']
            checkinglist = cammodel['search'].split(',')
            skip_begin = cammodel['begin']
            skip_finish = cammodel['finish']
            found = True
            break
    if not found:
      print('INFO: \'' + model + '\' not found, using defaults.')

print('INFO: -i ' + str(sample_interval) + ' -c ' + str(cut_trigger) + ' -d ' + str(min_segment_duration)+ ' -e ' + str(segment_extension) + ' -b ' + str(skip_begin) + ' -f ' + str(skip_finish))
print('      ' + str(checkinglist))

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
pushdir(Path(video_path).parent) # Change to video container directory

tmpdir = '~' + Path(video_name).stem
try:
  os.mkdir(tmpdir)
  pushdir(tmpdir) # Change to temporary directory
  print('INFO: Created temporary directory')
except OSError:
  sys.exit('Creation of the temporary directory failed')

os.system('ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 -i "' + video_path + '" > tmp')
duration = int(float(open('tmp', 'r').read().strip())) - skip_finish
if verbose: print('Duration: ' + str(duration))

print('INFO: Creating sample images')
for interval in range(skip_begin, duration, sample_interval):
  os.system('ffmpeg -v quiet -y -skip_frame nokey -ss ' + str(interval) + ' -i "' + video_path + '" -vf select="eq(pict_type\\,I),scale=800:-1" -an -q:v 3 -vframes 1 image-' + str(interval).zfill(7) + '.png')
if skip_finish < 1:
  os.system('ffmpeg -v quiet -y -skip_frame nokey -ss ' + str(duration - 1) + ' -i "' + video_path + '" -vf select="eq(pict_type\\,I),scale=800:-1" -an -q:v 3 -vframes 1 image-' + str(duration - 1).zfill(7) + '.png')

print('INFO: Analysing images')
with open('API-Results.txt',"w") as outfile:
  for filename in os.listdir(os.getcwd()):
    if filename.endswith(".png"):
      output  = detector.detect(filename)
      y = 0
      stringoutput = ''
  
      while y < len(output):
        match = re.search(r'\b[A-Z].*?\b', str(output[y]))
        stringoutput += str(match.group()) + '  '
    
        y +=1
      outfile.write(filename + '    ' + stringoutput + '\n')
      if verbose: print(filename + ' - ' + stringoutput)

with open('API-Results.txt',"r") as infile, open('output.txt',"w") as outfile:
  for line in infile:
    for check in checkinglist:
      if check in line:
        outfile.write(line)
        break

with open('output.txt',"r") as infile, open('list.txt',"w") as outfile:
  for line in infile:
    match = re.search(r'\d\d\d\d\d\d\d', line)
    x = int(match.group())
    imagelist.append(x)
    lines.append(line)

  while i < len(imagelist):
# variables
    last_element = len(imagelist) - 1
#avoid using elements not existent in list
    if i == 0: gap_to_prev_match = imagelist[i]
    else: gap_to_prev_match = imagelist[i] - imagelist[i - 1]
    if i == last_element: gap_to_next_match = imagelist[i]
    else: gap_to_next_match = imagelist[i + 1] - imagelist[i]
#added time between two samples if they were split apart by 1 second
    cut_duration = cut_trigger + 2 * segment_extension + 1
    segment_start = imagelist[i] - segment_extension
    segment_end = imagelist[i] + segment_extension
    
# case for finding the start of a segment
# if first element has matches in reach become beginning
# if previous match is too far away
    if (i == 0 and gap_to_next_match <= cut_duration) or (gap_to_prev_match > cut_duration):
      #save beginning timestamp
      if segment_start > 0: b = segment_start #only include segment_extension if timestamp doesn't become negative
      else: b = 0

# case for finding the end of a segment and finalizing it
# if next match is too far away
# if last element while previous match is close
    if (gap_to_next_match > cut_duration) or (i == last_element and gap_to_prev_match <= cut_duration):
      #save ending timestamp, only include segment_extension if timestamp doesn't exceed file duration
      if duration > segment_end: e = segment_end
      else: e = duration
      segment_duration = e - b
# finalize segment
# only finalize if the result would have non negative duration
# only finalize segment if long enough
      if (segment_duration >= 0) and (segment_duration >= min_segment_duration):
        beginnings.append(b)
        endings.append(e)

# else go to next sample without doing anything
    i += 1

  if verbose: print('Image list: ' + str(imagelist) + '\nBeginnings: ' + str(beginnings) + '\nEndings: ' + str(endings))

  print('INFO: Creating video segments')
  while p < len(beginnings):
    duration = endings[p] - beginnings[p]
    outfile.write('file ' + '\'out' + str(p) + '.mkv\'' + '\n')
    if verbose: print('ffmpeg -v quiet -vsync 0 -ss ' + str(beginnings[p]) + ' -i "' + video_path + '" -t ' + str(duration) + ' -c copy out' + str(p) + '.' + str(fileext))
    os.system('ffmpeg -v quiet -vsync 0 -ss ' + str(beginnings[p]) + ' -i "' + video_path + '" -t ' + str(duration) + ' -c copy out' + str(p) + '.' + str(fileext))
    p += 1

print('INFO: Creating final video')
if verbose: print('ffmpeg -v quiet -y -vsync 0 -safe 0 -f concat -i list.txt -c copy "' + video_path.rsplit('.', 1)[0] + '_recfilter-i' + str(sample_interval) + '-c' + str(cut_trigger) + '-d' + str(min_segment_duration) + '-e' + str(segment_extension) + '.' + str(fileext) + '"')
os.system('ffmpeg -v quiet -y -vsync 0 -safe 0 -f concat -i list.txt -c copy "' + video_path.rsplit('.', 1)[0] + '_recfilter-i' + str(sample_interval) + '-c' + str(cut_trigger) + '-d' + str(min_segment_duration) + '-e' + str(segment_extension) + '.' + str(fileext) + '"')

popdir() # Return to temporary directory parent
if (not keep): # Delete the temporary directory if no -keep
  print('INFO: Deleting temporary files')
  shutil.rmtree(tmpdir, ignore_errors=True)

popdir() # Return to initial directory
print('--- Finished ---\n')

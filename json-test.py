import json

rawdata = "[{'box': [310, 245, 424, 346], 'score': 0.8791205883026123, 'label': 'EXPOSED_BELLY'}, {'box': [274, 132, 310, 186], 'score': 0.8414173722267151, 'label': 'EXPOSED_ARMPITS'}, {'box': [296, 0, 423, 78], 'score': 0.8287931084632874, 'label': 'FACE_F'}, {'box': [290, 157, 381, 243], 'score': 0.805349588394165, 'label': 'EXPOSED_BREAST_F'}, {'box': [329, 341, 383, 377], 'score': 0.6137080788612366, 'label': 'EXPOSED_GENITALIA_F'}, {'box': [300, 358, 386, 441], 'score': 0.600153923034668, 'label': 'EXPOSED_GENITALIA_M'}, {'box': [446, 137, 491, 196], 'score': 0.5044803619384766, 'label': 'EXPOSED_ARMPITS'}]".replace("'","\"")
data = json.loads(rawdata)

for entry in data:
#  for coord in entry['box']:
#    print(coord)
  print(str(entry['box'][0]) + ',' + str(entry['box'][1]) + ',' + str(entry['box'][2]) + ',' + str(entry['box'][3]))
  print(entry['score'])
  print(entry['label'])

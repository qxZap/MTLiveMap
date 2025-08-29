import json

data = {}

police_lines = []
admin_lines = []
with open("police.txt",'r') as f:
    police_lines = f.readlines()
with open("admins.txt",'r') as f:
    admin_lines = f.readlines()

for line in police_lines:
    new_pd = line.replace('\n','')
    data[new_pd] = 'police'


for line in admin_lines:
    data[line.split('="')[1].split('"')[0]]="admin"

with open('players_ranks.json', 'w+') as f:
    f.write(json.dumps(data, indent=4))
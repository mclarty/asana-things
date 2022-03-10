import configparser
import json
import os.path
import requests
import urllib.parse
import xcall.xcall as xcall

# Read config file and set attributes; otherwise, create empty config file
config = configparser.ConfigParser()
if (os.path.exists('config.ini')):
    config.read('config.ini')
    asana_pat = config['Asana']['asana_pat']
    asana_workspaceid = config['Asana']['asana_workspaceid']
    asana_excluded_projects = config['Asana']['asana_excluded_projects']
    things_auth_token = config['Things']['things_auth_token']
else:
    config.add_section('Asana')
    config.set('Asana', 'asana_pat', '<<< SET ASANA PERSONAL ACCESS TOKEN >>>')
    config.set('Asana', 'asana_workspaceid', '<<< SET ASANA WORKSPACE ID >>>')
    config.set('Asana', 'asana_excluded_projects', '<<< SET CSV LIST OF EXCLUDED PROJECT IDS >>>')
    config.add_section('Things')
    config.set('Things', 'things_auth_token', '<<< SET THINGS AUTH TOKEN >>>')
    with open('config.ini', 'w') as configFile:
        config.write(configFile)
        configFile.flush()
        configFile.close()
    print ("Set the attributes in config.ini before running this script.")
    quit()

# Read Asana-Things KV table (asana-things.json)
if (os.path.exists('asana-things.json')):
    with open('asana-things.json') as f:
        task_kv = json.load(f)
    f.close()

# Initialize if no KV table file found
try:
    task_kv
except NameError:
    task_kv = {}

# Retrieve list of active tasks assigned to "me" and not in the projects set in asana_excluded_projects
url = ('https://app.asana.com/api/1.0/workspaces/{}/tasks/search?assignee.any=me&completed=false&is_blocked=false&projects.not={}'
    .format(asana_workspaceid, asana_excluded_projects))
headers = {
    'Accept': 'application/json',
    'Authorization': 'Bearer ' + asana_pat
    }
r = requests.get(url, headers=headers)

# Initialize task_list attribute
task_list = {}

# Loop through retrieved list of active tasks and add Asana ID to task_list dictionary
for task in r.json()['data']:
    task_list[task['gid']] = None

# Append list of Asana-Things KV pairs to task_list dictionary
if (task_kv is not None):
    task_list.update(task_kv)

# Loop through task_list dictionary and get updated task info from Asana
for asana_gid, things_id in task_list.items():
    url = 'https://app.asana.com/api/1.0/tasks/{}'.format(asana_gid)
    task_r = requests.get(url, headers=headers)

    # If no data is found for task from Asana, ignore and continue the loop
    if ('data' in task_r.json()):
        task_detail = task_r.json()['data']
    else:
        continue

    # Initialize Things JSON query dictionary
    dict = []

    # If the Asana-Things KV table has a Things ID, it's an update to an existing record
    if (task_list[asana_gid] is not None):
        operation = "update"
        task_id = things_id
    # Otherwise create a new Things to-do record
    else:
        operation = "create"
        task_id = None

    # Initialize Asana attributes dictionary
    attributes = {}
    # attributes['list-id'] = "J5qoUwSxiCMTKUJcZFkfbn" # Send to inbox instead of Work list
    attributes['title'] = task_detail['name']
    if ('completed' in task_detail):
        attributes['completed'] = task_detail['completed']
    if ('due_on' in task_detail):
        attributes['deadline'] = task_detail['due_on']
    if ('notes' in task_detail):
        attributes['notes'] = task_detail['notes']
        if (task_detail['notes'] != '' and 'permalink_url' in task_detail):
            attributes['notes'] += "\n\n" + task_detail['permalink_url']
        elif ('permalink_url' in task_detail):
            attributes['notes'] = task_detail['permalink_url']

    # Insert obligatory JSON attributes to query string
    dict.append({'type': 'to-do', 'operation': operation, 'id': task_id, 'attributes': attributes})

    # Convert Things query from dictionary to JSON string and URL encode
    api_json = json.dumps(dict)
    api_query = urllib.parse.quote(api_json)

    # Execute X-Callback for Things, get resulting Things ID
    result = xcall.xcall('things', 'json?auth-token=' + things_auth_token + '&data=' + api_query)
    result_json = result['x-things-ids']
    result_obj = json.loads(result_json)

    # If Asana says task is completed, remove from Asana-Things KV table; otherwise, add Things ID to the Asana KV pair
    if (task_detail['completed'] is True):
        task_kv.pop(asana_gid, None)
    else:
        task_kv[asana_gid] = result_obj[0]

# Write the final version of the Asana-Things KV table to file
f = open('asana-things.json', 'w')
json.dump(task_kv, f)
f.close()

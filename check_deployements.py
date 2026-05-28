import requests

r = requests.post(
    'https://sap-joulestudio-training.authentication.eu10.hana.ondemand.com/oauth/token',
    data={'grant_type': 'client_credentials'},
    auth=('sb-c06d539a-4ccc-40cb-950a-1cb127c1802d!b632983|aicore!b540',
          '395b6fec-98fe-404a-b377-8a525f5593ee$SY-GDUrmyuFXGBub3g0mav7VrTSRuUoDFq6o0wWAJ4s=')
)
print(f"Auth status: {r.status_code}")
token = r.json().get('access_token')
if not token:
    print(f"Auth failed: {r.text}")
    exit()

print("Auth OK - listing deployments...\n")

deps = requests.get(
    'https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com/v2/lm/deployments',
    headers={'Authorization': f'Bearer {token}', 'AI-Resource-Group': 'default'},
    params={'status': 'RUNNING'}
).json()

resources = deps.get('resources', [])
print(f"Found {len(resources)} running deployment(s):\n")

for d in resources:
    dep_id = d.get('id', '?')
    model = d.get('details', {}).get('resources', {}).get('backend_details', {}).get('model', {}).get('name', 'unknown')
    scenario = d.get('scenarioId', '')
    print(f"  ID: {dep_id}")
    print(f"  Model: {model}")
    print(f"  Scenario: {scenario}")
    print()
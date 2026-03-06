"""
List all Intercom Help Centers (e.g. FundedNext Help Center).
Use this to verify the API returns your help centers and their ids.
"""
from dotenv import load_dotenv
load_dotenv()

from intercom_client import IntercomClient

client = IntercomClient()
# Raw GET /help_center/help_centers
import requests
r = requests.get(
    "https://api.intercom.io/help_center/help_centers",
    headers=client.headers,
)
print("GET /help_center/help_centers")
print("Status:", r.status_code)
data = r.json()
print("Keys:", list(data.keys()))
if "data" in data:
    hcs = data["data"]
    print(f"Number of Help Centers: {len(hcs)}")
    for hc in hcs:
        print(f"  id={hc.get('id')}  display_name={repr(hc.get('display_name'))}  identifier={repr(hc.get('identifier'))}  name={repr(hc.get('name'))}")
else:
    print("Response (first 500 chars):", str(data)[:500])

print("\nget_help_centers() via client:")
hcs = client.get_help_centers()
print(f"  Count: {len(hcs)}")
for hc in hcs:
    print(f"  id={hc.get('id')}  display_name={repr(hc.get('display_name'))}  identifier={repr(hc.get('identifier'))}")

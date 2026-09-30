import argparse
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

p = argparse.ArgumentParser()
p.add_argument("url")
a = p.parse_args()
s = boto3.Session()
r = AWSRequest(method="GET", url=a.url)
SigV4Auth(
    s.get_credentials().get_frozen_credentials(), "execute-api", s.region_name or "ap-southeast-2"
).add_auth(r)
response = requests.get(a.url, headers=dict(r.headers), timeout=30)
print(response.status_code, response.text)
response.raise_for_status()

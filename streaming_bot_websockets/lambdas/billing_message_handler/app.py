import json
import boto3 

def lambda_handler(event, context):
    response = {"statusCode": 200}
    print("Received event in Billing handler: " + json.dumps(event, indent=2))
    return response
    





import json
import boto3 
import os
from utils.chatbot_utils import invoke_model,log_to_db



def lambda_handler(event, context):
    events_table_name = os.environ['EVENTS_TABLE_NAME']
    response = {"statusCode": 200}
    print("Received event in Sentiment handler: " + json.dumps(event, indent=2))
    request_id = event['detail']['msg_id']
    session_id = event['detail']['session_id']
    user_msg = event['detail']['user_msg']
    if event['detail-type'] == "com.onebyzero.chatter.chat_message":
        prompt = f"You are a chat admin policing chat messages, analyse the message in <msg> and \
                 provide only a json object as a repsonse, dont add anything other than a json object in the response.\
                 Here are  the required fields,\
                 sentiment - positive or negative \
                 language - two letter code of the language \
                 emotion - happy,sad \
                 <msg>{user_msg}</msg>"
        bedrock_client = bedrock_client = boto3.client(service_name='bedrock-runtime')
        senti_analysis_response =invoke_model(bedrock_client,prompt)
        json_evt = json.loads(senti_analysis_response)
        log_to_db(pk=session_id,
                  sk=f"{request_id}#sentiment_analysis",
                  table_name=events_table_name,
                  event_json_obj=json_evt)
    return response
    





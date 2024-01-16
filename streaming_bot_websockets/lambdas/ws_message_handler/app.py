import json, urllib.parse
import boto3
import os
from uuid import uuid4
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, helpers
from utils.chatbot_utils import invoke_model, invoke_model_with_streaming_response, \
                                search_index, log_to_db, text_embedding, send_message, send_to_msg_bus 
                                

ws_api_url = os.environ['WS_API_URL']
#Remove all hardcoding, TODO
ws_client = boto3.client('apigatewaymanagementapi',endpoint_url=ws_api_url)
evt_bus_name = os.environ['EVENT_BUS_NAME']
host = urllib.parse.urlparse(os.environ['OPENSEARCH_EP']).netloc #replace this with the value from the AWS Management Console
region = os.environ['AWS_DEFAULT_REGION']
is_streaming = os.environ["LLM_STREAMING_ENABLED"]
events_table_name = os.environ['EVENTS_TABLE_NAME']

service = "aoss"
credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(credentials, region, service)
index_name = "docs-index"

client = OpenSearch(
    hosts = [{"host": host, "port": 443}],
    http_auth = auth,
    use_ssl = True,
    verify_certs = True,
    connection_class = RequestsHttpConnection,
    pool_maxsize = 20
)


def lambda_handler(event, context):
    
    #print("Received event: " + json.dumps(event, indent=2))
    connection_id = event['requestContext']['connectionId']
    print(f"Connection Id: {connection_id}")
    domain = event.get("requestContext", {}).get("domainName")
    stage = event.get("requestContext", {}).get("stage")
    endpoint_url = f"https://{domain}/{stage}"
    print(f"Endpoint URL for response: {endpoint_url}")
    
    # Check WebSocket event type
    if event['requestContext']['eventType'] == 'CONNECT':
        # Handle connect event
        print("CONNECT event: ")
        response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'Connect successful'}),
        }
    elif event['requestContext']['eventType'] == 'DISCONNECT':
        # Handle disconnect event
        print("DISCONNECT event: ")
        response = {
            'statusCode': 200,
            'body': json.dumps({'message': 'Disconnect successful'}),
        }
    elif event['requestContext']['eventType'] == 'MESSAGE':
        # Handle data event
        request_id = str(uuid4())
        bedrock_client = boto3.client(service_name='bedrock-runtime',
                                      region_name=region)
        message = event['body']
        
        print(f"MESSAGE event: {message}")
        vector = text_embedding(bedrock_client,message)
        response = search_index(client,"docs-index",vector,no_of_results=2)
        data=response['hits']['hits']
        print(f"We have {len(data)} context retrieved")
        context=""
        context_arr = []
        for item in data:
            context = f"{context} {item['_source']['doc_text']}"
            context_arr.append(item['_source']['doc_text'])
            print(f"Length of item Context: {len(item['_source']['doc_text'])}")
        print(f" Context: {context} \n Context array {context_arr}")
        query_with_context = f"I'm a virtual Agent, answer the question in <question> \
            with the provided context in <context> \
            <question>{message}</question> <context>{context}</context>"

        if is_streaming == "YES":
            stream = invoke_model_with_streaming_response(bedrock_client,query_with_context)
            if stream:
                for event in stream:
                    chunk = event.get('chunk')
                    if chunk:
                        data = json.loads(chunk.get('bytes').decode())
                        send_message(ws_client,connection_id,data['completion'].strip())
    
            response = {
                'statusCode': 200
            }
        else:
            response_message = invoke_model(bedrock_client,query_with_context)
            send_message(ws_client,connection_id,response_message)
            pk_str = f"{connection_id}"
            sk_str = f"{request_id}"
            event = {
                "msg_id": request_id,
                "session_id": connection_id,
                "event_type": "com.onebyzero.chatter.chat_message",
                "user_msg": message,
                "ai_msg": response_message,
                "context": context_arr,
                "query_with_prompt": query_with_context
            }
            #Customer first, logging later
            send_message(ws_client,connection_id,json.dumps(logged_evt))
            logged_evt = log_to_db(pk=pk_str, \
                                   sk=sk_str,\
                                   table_name=events_table_name, \
                                   event_json_obj=event)
            send_to_msg_bus(evt_bus_name,event)
            
    else:
        # Return an error for unknown event types
        print("UNKNOWN event: ")
        response = {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid event type'}),
        }

    return response





    
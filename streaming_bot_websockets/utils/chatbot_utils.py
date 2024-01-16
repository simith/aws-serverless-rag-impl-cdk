import json
import boto3 

def invoke_model(bedrock_client,prompt):

    print(f"Entering invokde_model with prompt: {prompt}")
    config={
      "maxTokenCount": 1000,
      "stopSequences": [],
      "temperature":0.1,
      "topP":1
    }
    body = json.dumps({
        "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
        "max_tokens_to_sample": 300,
        "temperature": 0.5,
        "top_p": 0.6,
    })
    response = bedrock_client.invoke_model(
    modelId='anthropic.claude-v2:1',
    body=body
    )

    response_body = json.loads(response.get('body').read())

    # text
    finished_response = response_body.get('completion')
    return finished_response


def invoke_model_with_streaming_response(bedrock_client,prompt):
    print(f"Entering invokde_model with prompt: {prompt}")
    config={
      "maxTokenCount": 1000,
      "stopSequences": [],
      "temperature":0.1,
      "topP":1
    }
    #modelId='amazon.titan-tg1-large', 
    #body = json.dumps({'inputText': prompt,'textGenerationConfig':config})
    #body = json.dumps({"prompt": "\n\nHuman: story of two dogs\n\nAssistant:", "max_tokens_to_sample" : 300})
    body = json.dumps({
        "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
        "max_tokens_to_sample": 300,
        "temperature": 0.1,
        "top_p": 0.9,
    })
    response = bedrock_client.invoke_model_with_response_stream(
    modelId='anthropic.claude-v2', 
    body=body)

    stream = response.get('body')

    return stream


def text_embedding(bedrock_client,text):
    body=json.dumps({"inputText": text})
    response = bedrock_client.invoke_model(body=body, modelId='amazon.titan-embed-text-v1', accept='application/json', contentType='application/json')
    response_body = json.loads(response.get('body').read())
    embedding = response_body.get('embedding')
    return embedding


def search_index(client,index_name,vector,no_of_results):
    
    document = {
        "size": 5,
        "_source": {"excludes": ["doc_vector"]},
        "query": {
            "knn": {
                 "doc_vector": {
                     "vector": vector,
                     "k":no_of_results
                 }
            }
        }
    }
    response = client.search(
    body = document,
    index = index_name
    )
    return response


def log_to_db(pk,sk,table_name,event_json_obj):
    
    dynamodb = boto3.resource('dynamodb')
    events_table_ref = dynamodb.Table(table_name)
    event = {}
    event['pk'] = pk
    event['sk'] = sk
    event['body'] = event_json_obj
    print(f"Logging event to DynamoDb {event}")
    events_table_ref.put_item(
        Item=event)
    return event

def send_message(ws_client,connection_id, message):
    """
    Send a message to a specific WebSocket connection.
    """
    try:
        response = ws_client.post_to_connection(
            ConnectionId=connection_id,
            Data=message
        )
        print("Message sent successfully:", response)
    except Exception as e:
        print("Error sending message:", e)


def send_to_msg_bus(evt_bus_name,event):
    eb_client = boto3.client('events')
    response = eb_client.put_events(
    Entries=[
        {
            'Source': 'com.onebyzero.chatter.chat_message',
            'Resources': [
                'string',
            ],
            'DetailType': 'com.onebyzero.chatter.chat_message',
            'Detail': json.dumps(event),
            'EventBusName': evt_bus_name
        }
    ]
    )
    return response
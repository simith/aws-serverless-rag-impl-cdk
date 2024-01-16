import json
import boto3 
import os
import urllib.parse
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, helpers

bedrock = boto3.client(
 service_name='bedrock-runtime'
)
host = urllib.parse.urlparse(os.environ['OPENSEARCH_EP']).netloc #replace this with the value from the AWS Management Console
region = os.environ['AWS_DEFAULT_REGION']
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


def create_index_for_documents(index_name):
    
    index_body = {
        "mappings": {
            "properties": {
                "doc_text": {"type": "text"},
                "doc_vector": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "engine": "nmslib",
                        "space_type": "cosinesimil",
                        "name": "hnsw",
                        "parameters": {"ef_construction": 512, "m": 16},
                    },
                },
            }
        },
        "settings": {
            "index": {
                "number_of_shards": 2,
                "knn.algo_param": {"ef_search": 512},
                "knn": True,
            }
        },
        }
    try:
        response = client.indices.create(index_name, body=index_body)
        print(json.dumps(response, indent=2))
    except Exception as ex:
        print(ex)

def check_if_index_exists(index_name):
    l_return = 0
    try:
        print(client.indices.get(index_name))
        l_return = 1
    except Exception as ex:
        print(ex)
    return l_return

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    try:
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        filename = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
        print(f'Bucket name: {bucket_name}')
        print(f'Object/File name: {filename}')
        '''If index does not exist create one'''
        if check_if_index_exists(index_name) == 0:
            print("Index not found, creating index now...")
            create_index_for_documents(index_name)
        else:
            print("Index present, progress with ingestion")
    
        storage_file = f"/tmp/{filename}"
        s3 = boto3.resource('s3')
        s3.meta.client.download_file(bucket_name, \
                                    filename, storage_file)
        loader = PyPDFLoader(storage_file)
        documents = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=100)
        document_paras = text_splitter.split_documents(documents)

        print(f"Number of pages being ingested to Opensearch: {len(document_paras)}")
        for para in document_paras:
            v_embedding = text_embedding(para.page_content)
            add_document(v_embedding,para.page_content)
        print("Finished ingestion")   

    except Exception as e:
        print(f"Exception hit during ingest {str(e)}")


def add_document(vector,text):
    document = {
      "doc_vector": vector,
      "doc_text": text
    }
    
    response = client.index(
        index = index_name,
        body = document
    )
    print('\nAdding document:')
    print(response) 

    #loader = PyPDFLoader("example_data/layout-parser-paper.pdf")
    #pages = loader.load_and_split()

def text_embedding(text):
    body=json.dumps({"inputText": text})
    response = bedrock.invoke_model(body=body, modelId='amazon.titan-embed-text-v1', accept='application/json', contentType='application/json')
    response_body = json.loads(response.get('body').read())
    embedding = response_body.get('embedding')
    return embedding  



def search_index(index_name,vector,no_of_results):
    
    document = {
        "size": 15,
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




import streamlit as st
import boto3
import json
import awswrangler as wr
import re
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor
import pandas as pd
from botocore.exceptions import ClientError

secret_name = "drillreportapp1"
region_name = "us-east-1"
glue_database_name = 'drillingreport'
table_name='kv'

PROMPT_TEMPLATE="""
    Context: I have an Athena table called kv. The table has field 'well_name','operator','current_operations','planned_operations','safety_summary','report_date'. 
    The schema for the tables are: "well_name" (string), "operator" (string), 'safety_summary' (string), 'current_operations' (string),'planned_operations' (string), "report_date" (string).

    Instruction: write a SQL query that return report_date there is no safety incident
    SQL: SELECT distinct report_date FROM "drillingreport"."kv"  where lower("safety_summary" ) LIKE '%no incident%'
    
    Instruction: write a SQL query that return total number of well
    SQL: SELECT COUNT(DISTINCT well_name) FROM "drillingreport"."kv" 
    
    Instruction: write a SQL query that return report date there is bop activity in current operations
    SQL: SELECT DISTINCT report_date FROM "drillingreport"."kv"  WHERE lower("current_operations")  LIKE '%bop%'
  
    Instruction: write a SQL query that return {INSTRUCTION}
    SQL:
    """
    
def get_secret():

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    secret = get_secret_value_response['SecretString']

    return secret

secret = get_secret()
secret = json.loads(secret)
ENDPOINT_NAME = secret['ENDPOINT_NAME']
AWS_SECRET_ACCESS_KEY = secret['AWS_SECRET_ACCESS_KEY']
AWS_ACCESS_KEY_ID = secret['AWS_ACCESS_KEY_ID']
ACCOUNT_NO=secret['ACCOUNT_NO']

@st.cache_data(persist=True)
def query_endpoint(payload,endpoint_name):
    client = boto3.client('runtime.sagemaker',region_name=region_name)
    response = client.invoke_endpoint(EndpointName=endpoint_name, ContentType='application/json', Body=json.dumps(payload).encode('utf-8'))
    model_predictions = json.loads(response['Body'].read())
    generated_text = model_predictions[0]['generated_text']
    # print(
    # f"Input Text: {payload['inputs']}{newline}"
    # f"Generated Text: {bold}{generated_text}{unbold}{newline}")
    return generated_text

@st.cache_data(persist=True)
def parse_sqlquery(gen_text):
    if '<code>' in gen_text and '</code>' in gen_text:
        code_content=re.search('<code>(.*?)</code>',gen_text.replace('\n',' '))
        code_content_group=code_content.group(1)
        sql_code_content=code_content_group
    # elif re.search('```(.*?)```',gen_text.replace('\n',' ')):
    #     code_content=re.search('```(.*?)```',gen_text.replace('\n',' '))
    else:
        code_content=re.search(r'^\s*SELECT.*',gen_text.strip())
        code_content_group=code_content.group()
        sql_code_content=code_content_group  
                
    if sql_code_content:
        sql_code_content=sql_code_content.replace('\n','')
        sql_query=sql_code_content.replace("\\'","'").replace('\n',' ')
        print('SQL Code:\n',sql_query)
            
    return sql_query

# def query_athena():
#     try:
#         test=pd.read_sql(st.session_state.sql_query,conn)
#         athena_response=str(test.values.tolist())
#     except:
#         athena_response='Cannot run Athena query'
#     st.session_state.sql_results=athena_response

def update_sqlquery(sql_query):
    st.session_state.sql_query=sql_query
    
def get_table_schema():
    ### get table schema:
    table_schema_query="""select column_name,data_type
                            from information_schema.columns
                            where table_name='kv'
                        """
    ## Run Athena query to get table schema:
    try:
        conn=connect(aws_access_key_id=AWS_ACCESS_KEY_ID,
                     aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            s3_staging_dir=f's3://aws-athena-query-results-{ACCOUNT_NO}-us-east-1/staging/',
            region_name=region_name,
            cursor_class=PandasCursor)
        df_schema=pd.read_sql(table_schema_query,conn)
    except:
        df_schema=pd.DataFrame()
    # st.write("DrillingReport Table schema:")
    # st.dataframe(df_schema)
    return df_schema
    
def app():

    boto3.setup_default_session(region_name=region_name,
                                aws_access_key_id=AWS_ACCESS_KEY_ID,
                                aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    st.title("GENergyInsights - Drilling Report Q&A app")
    if 'sql_query' not in st.session_state:
        st.session_state.sql_query=''
        
    col1, col2 = st.columns([2,5])
    
    with col1:
        st.write(f"Drilling Report Table name: {glue_database_name}.{table_name}")
        df_schema=get_table_schema()
        st.write("Drilling Report Table schema:")
        st.dataframe(df_schema)
        
    with col2:
        ### user input:
        user_input=st.text_area("Enter your text here:",key="user_text",height=100)
        
        
        if st.button("Generat Text"):

            INSTRUCTION=user_input
            INPUTS=PROMPT_TEMPLATE.replace('{INSTRUCTION}',INSTRUCTION)

            payload = {
                "inputs":INPUTS ,
                "parameters":{
                    "max_new_tokens": 100
                }
            }
            
            ## send to LLM Text-to-SQL:
            gen_text=query_endpoint(payload,ENDPOINT_NAME)
            gen_text=gen_text.split('\n')[0]
            st.write("Generated Text:")
            st.write(gen_text)
            
            ## parse SQL from generated text:
            try:
                sql_code_content=parse_sqlquery(gen_text)
            except:
                sql_code_content=gen_text
            sql_query=sql_code_content.replace("\\'","'").replace('\n',' ')
            #sql_query=st.text_area("SQL Query:",value=sql_query)
            sql_query=st.text_area(label="SQL Query:",value=sql_query,on_change=update_sqlquery,args=[sql_query],height=100)
            st.session_state.sql_query=sql_query
            ## Run Athena query:
            try:
                conn=connect(aws_access_key_id=AWS_ACCESS_KEY_ID,
                     aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    s3_staging_dir=f's3://aws-athena-query-results-{ACCOUNT_NO}-us-east-1/staging/',
                    region_name=region_name,
                    cursor_class=PandasCursor)
                test=pd.read_sql(sql_query,conn)
                athena_response=str(test.values.tolist())
            except:
                athena_response='Cannot run Athena query'
            
            # st.text_input(label="SQL Query (edit then rerun automatically):",value=st.session_state.sql_query,on_change=query_athena)
            # st.text_input(label="Query Results:",value=st.session_state.sql_results)
            
            st.write("Query Results:")
            st.write(athena_response)
            

        if st.button("Query Database"):
            sql_query=st.session_state.sql_query
            sql_query=st.text_area(label="SQL Query:",value=sql_query,on_change=update_sqlquery,args=[sql_query],height=100)
            st.session_state.sql_query=sql_query
            st.write("New SQL query :")
            st.write(sql_query)
            try:
                conn=connect(aws_access_key_id=AWS_ACCESS_KEY_ID,
                     aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                        s3_staging_dir=f's3://aws-athena-query-results-{ACCOUNT_NO}-us-east-1/staging/',
                        region_name=region_name,
                        cursor_class=PandasCursor)
                test=pd.read_sql(sql_query,conn)
                athena_response=str(test.values.tolist())
            except:
                athena_response='Cannot run Athena query'

            st.write("Query Results:")
            st.write(athena_response)

    
if __name__=='__main__':
    app()
                       
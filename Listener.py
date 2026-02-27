#!/usr/bin/python
import json
import os
import requests
import socket
import time
from datetime import datetime, timedelta, timezone
from time import sleep
from azure.storage.blob import BlobServiceClient
from azure.identity import ClientSecretCredential
from azure.core.exceptions import ResourceExistsError


# Provide your Azure AD app details
tenant_id = "<tenant_id>"
client_id = "<client_id>"
client_secret = "<client_secret>"

# Initialize ClientSecretCredential
clSeccredential = ClientSecretCredential(tenant_id, client_id, client_secret)


# The URL to access the metadata service
# local testing URL (uncomment for local testing with mock server)
#metadata_SEurl ="http://127.0.0.1/metadata/scheduledevents"
# Retrieve Scheduled Events from Azure IMDS
metadata_SEurl ="http://169.254.169.254/metadata/scheduledevents"
# This must be sent otherwise the request will be ignored
SEheader = {'Metadata' : 'true'}
# Current version of the API
SEquery_params = {'api-version':'2020-07-01'}


# Retrieve VM metadata from Azure IMDS, fall back to hostname / empty strings
def _imds_computetext(field: str) -> str:
    resp = requests.get(
        f"http://169.254.169.254/metadata/instance/compute/{field}",
        headers={"Metadata": "true"},
        params={"api-version": "2021-02-01", "format": "text"},
        timeout=2
    )
    return resp.text.strip()

try:
    vm_name         = _imds_computetext("name")
    subscription_id = _imds_computetext("subscriptionId")
    resource_group  = _imds_computetext("resourceGroupName")
except Exception:
    vm_name         = socket.gethostname()
    subscription_id = ""
    resource_group  = ""

def write_preempt_event(event):
    # Build the entity (same as tststrtbl.py)
    row_key = f"{'EventId'}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

    # Append VM metadata to the event payload
    event["DetectedAt"] = datetime.now(timezone.utc).isoformat()
    event["VMName"] = vm_name
    event["SubscriptionId"] = subscription_id
    event["ResourceGroup"] = resource_group

    # Blob path: RestartVM/<RowKey>.json
    blob_name = f"RestartVM/{row_key}.json"
    blob_content = json.dumps(event, indent=2).encode("utf-8")
    with BlobServiceClient(
        account_url="https://<storageaccount>.blob.core.windows.net",
        credential=clSeccredential
    ) as blob_service_client:
        blob_client = blob_service_client.get_blob_client(
            container="spotvmentity",
            blob=blob_name
        )
        blob_client.upload_blob(blob_content, overwrite=True)
        print(f"Entity written to blob spotvmentity/{blob_name} successfully.")


def get_scheduled_events():           
    resp = requests.get(metadata_SEurl, headers = SEheader, params = SEquery_params)
    print(resp)
    data = resp.json()
    return data

def confirm_scheduled_event(event_id):  
    # This payload confirms a single event with id event_id
    # You can confirm multiple events in a single request if needed      
    payload = json.dumps({"StartRequests": [{"EventId": event_id }]})
    response = requests.post(metadata_SEurl, 
                            headers= SEheader,
                            params = SEquery_params, 
                            data = payload)    
    return response.status_code

def log(event): 
    # This is an optional placeholder for logging events to your system 
    print(event["Description"])
    return

def advanced_sample(last_document_incarnation): 
    # Poll every second to see if there are new scheduled events to process
    # Since some events may have necessarily short warning periods, it is 
    # recommended to poll frequently
    found_document_incarnation = last_document_incarnation
    while (last_document_incarnation == found_document_incarnation):
        sleep(1)
        payload = get_scheduled_events()    
        found_document_incarnation = payload["DocumentIncarnation"]        
        
    # We recommend processing all events in a document together, 
    # even if you won't be actioning on them right away
    for event in payload["Events"]:
        print(event)
        # Events that have already started, logged for tracking
        if (event["EventStatus"] == "Started"):
            log(event)

        elif (event["EventType"] == "Preempt"):
            log(event)
            write_preempt_event(event)
            

        # Approve all user initiated events. These are typically created by an 
        # administrator and approving them immediately can help to avoid delays 
        # in admin actions
        elif (event["EventSource"] == "User"):
            confirm_scheduled_event(event["EventId"])            
            
        # For this application, freeze events less that 9 seconds are considered
        # no impact. This will immediately approve them
        elif (event["EventType"] == "Freeze" and 
            int(event["DurationInSeconds"]) >= 0  and 
            int(event["DurationInSeconds"]) < 9):
            confirm_scheduled_event(event["EventId"])
            
        # Events that may be impactful (for example reboot or redeploy) may need custom 
        # handling for your application
        else: 
            #TODO Custom handling for impactful events
            log(event)
    print("Processed events from document: " + str(found_document_incarnation))
    
    return found_document_incarnation

def main():
    # This will track the last set of events seen 
    last_document_incarnation = "-1"
    # the task scheduler granularity is 5 minutes, so this sample will run for 5 minutes before exiting and within this 5 minutes it will poll for new events every 5 seconds. You can adjust this as needed
    max_duration = timedelta(minutes=5)
    poll_interval = 5  # seconds
    start_time = datetime.now(timezone.utc)

    while (datetime.now(timezone.utc) - start_time) < max_duration:
        last_document_incarnation = advanced_sample(last_document_incarnation)
        sleep(poll_interval)

    print("Reached 5-minute time limit. Exiting.")

if __name__ == '__main__':
    main()



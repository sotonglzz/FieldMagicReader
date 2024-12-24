import requests
import json
from base64 import b64encode
from flask import Flask, render_template

# Initialized variables
next_token=""
counter=0
jobs =[]

# Function to encode FieldMagic API Key and API Secret
def basic_auth(username, password):
    token = b64encode(f"{username}:{password}".encode('utf-8')).decode("ascii")
    return f'Basic {token}'

# FieldMagic API Key and API Secret
username = "c3d1beb4687f6a20"
password = "310b7da2d2fe630739fa6a12"

# Initializing JSON request from FieldMagic API
payload=json.dumps([
  {"next_token": next_token}
])
headers = {
  'Authorization': basic_auth(username,password),
  'Content-Type': 'application/json',
  'Client-Id': 'b48698b2-d589-4b64-af1f-4482e7fbe599',
}

#Run the first time
# FieldMagic API URL to extract all job listings
url = "http://api.fieldmagic.co/jobs?next_token="+next_token+"&date_modified"
# Pinging FieldMagic API to extract data
response = requests.request("GET", url, headers=headers, data=payload)
# Parsing Data into JSON
data = response.json()
jobs=data
#print(jobs)

#print(response.text) # Debug line to print 

# Extract job number, job summary, and job location, ignoring completed jobs
job_details = [
  {
    "job_number": job["job_number"],
    "job_summary": job["job_summary"],
    "job_location": job["address_text"]
    }
  for job in data["data"]
  if not job["date_completed"]  # Ignore jobs with a non-empty date_completed
  ]

# Print the job details
for job in job_details: 
  counter += 1
  #print(f"Job Number: {job['job_number']}\nJob Location: {job['job_location']}\nJob Summary: {job['job_summary']}\n")
  print(job['job_number'])
  #print(counter)
  jobs.update(job)
  
next_token = data["next_token"]

while next_token:
      # FieldMagic API URL to extract all job listings
      url = "http://api.fieldmagic.co/jobs?next_token="+next_token+"&date_modified"
      # Pinging FieldMagic API to extract data
      response = requests.request("GET", url, headers=headers, data=payload)
      # Parsing Data into JSON
      data = response.json()
      #print(jobs)

      #print(response.text) # Debug line to print 

      # Extract job number, job summary, and job location, ignoring completed jobs
      job_details = [
        {
          "job_number": job["job_number"],
          "job_summary": job["job_summary"],
          "job_location": job["address_text"]
          }
        for job in data["data"]
        if not job["date_completed"]  # Ignore jobs with a non-empty date_completed
        ]

      # Print the job details
      for job in job_details: 
        counter += 1
        #print(f"Job Number: {job['job_number']}\nJob Location: {job['job_location']}\nJob Summary: {job['job_summary']}\n")
        print(job['job_number'])
        jobs.update(job)
      
      if data['next_token']=="":
            next_token = data["next_token"]
      else: 
        print("End of Tokens")
        break
      
#print(jobs)
#print("hello")      
      

#Back-up Data
#FieldMagic client ID = b48698b2-d589-4b64-af1f-4482e7fbe599
#FieldMagic API key = c3d1beb4687f6a20
#FieldMagic API secret = 310b7da2d2fe630739fa6a12
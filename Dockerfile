# Use the official Python image as the base image
FROM python:3.8-slim-buster

RUN apt-get -y update && apt-get install -y curl

RUN pip3 install pandas==2.0.2 boto3==1.26.156 fsspec==2021.08.1 s3fs streamlit pyathena==2.25.2 awswrangler==3.2.1
# Set the working directory to /app
WORKDIR /app

# Copy the requirements file into the container and install dependencies
# COPY requirements.txt .
# RUN pip install -r requirements.txt

# Copy the rest of the app files into the container
COPY . .

# Expose the port that Streamlit runs on
EXPOSE 8501

# Set the command to run when the container starts
CMD ["streamlit", "run", "app.py"]

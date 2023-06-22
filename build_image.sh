
namespace='streamlit-app-chatbot'
region=$(aws configure get region)
account=$(aws sts get-caller-identity --query Account --output text)

aws ecr get-login-password --region "${region}" | docker login --username AWS --password-stdin "${account}".dkr.ecr."${region}".amazonaws.com

# check if repo does not exist to create it
aws ecr describe-repositories --repository-names "${namespace}" > /dev/null 2>&1

if [ $? -ne 0 ]
then
    aws ecr create-repository --repository-name "${namespace}" > /dev/null
fi
# including the base algorithm and version to keep track of the origins of our custom container
fullname="${account}.dkr.ecr.${region}.amazonaws.com/${namespace}"
echo $fullname
docker build -f Dockerfile . -t streamlit-app
docker tag streamlit-app  $fullname
docker push $fullname

#aws lambda update-function-code --function-name lambda_webscraper_cft --image-uri $fullname:latest
#aws lambda update-function-code --function-name rate_card_processor_cft --image-uri $fullname:latest
Features

1.User authentication (Sign up / Log in) with JWT tokens

2.Generate analogies for technical concepts

3.View and store history of generated analogies

4.Quiz generation based on analogies

5.Responsive frontend interface

6.Compatible with local, Docker, and Kubernetes deployment



Local Setup

1.Clone the repository:
git clone <your-repo-url>
cd instant-analogy



2.Backend setup:

cd backend

python -m venv venv

venv\Scripts\activate   # Windows

source venv/bin/activate # Linux/Mac

pip install -r requirements.txt

uvicorn main:app --reload



3.Frontend setup:
cd frontend
python -m http.server 5500




4.Docker Setup
docker compose build
docker compose up -d

Access:

Frontend: http://127.0.0.1:5500

Backend: http://127.0.0.1:8000





Kubernetes Setup (Minikube)

1.minikube start

2.Apply deployments and services:

kubectl apply -f k8s/backend-deployment.yaml

kubectl apply -f k8s/frontend-deployment.yaml

3.Access frontend via NodePort:

minikube service frontend-service




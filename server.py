from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from flask_pymongo import PyMongo
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

ACCOUNT_NAME = 'passionfroid'
ACCOUNT_KEY = 'HuL6tfRJysTzKJDgo0YG/ML6M1UYJMdmFUEHUEvobVrB6SesnqJPkvAfq/6W7/mN+NfTl1V/5mIo+AStuFfDWg=='
CONTAINER_NAME = 'passion-froid'
BLOB_SERVICE = BlobServiceClient(account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net", credential=ACCOUNT_KEY)

app.config["MONGO_URI"] = "mongodb://localhost:27017/passionFroid"
mongo = PyMongo(app)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/upload', methods=['POST'])
def upload_image():
    image = request.files.get('image')
    other_field = request.form.get('otherField')

    if not image:
        print(request.files)
        print(request.form)
        return jsonify({'error': 'No image provided'}), 400

    # Enregistrement de l'image
    image_path = os.path.join(UPLOAD_FOLDER, secure_filename(image.filename))
    image.save(image_path)

    # Upload to Azure Blob Storage
    blob_client = BLOB_SERVICE.get_blob_client(container=CONTAINER_NAME, blob=secure_filename(image.filename))
    with open(image_path, "rb") as data:
        blob_client.upload_blob(data)
    blob_url = blob_client.url
    
    # Supprimer l'image locale après l'envoi
    os.remove(image_path)

    # Insertion des données dans MongoDB
    data = {
        'image_path': blob_url,   # Utilisez l'URL du blob au lieu du chemin local
        'other_field': other_field
    }
    mongo.db.images.insert_one(data)

    return jsonify({'message': 'Success'}), 200

if __name__ == "__main__":
    app.run(debug=True)

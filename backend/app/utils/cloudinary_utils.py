import cloudinary
import cloudinary.uploader
import cloudinary.api
import pickle
import io
import os
import logging
import urllib.request
from flask import current_app

logger = logging.getLogger(__name__)

def init_cloudinary():
    """Initialize cloudinary configuration if not already configured"""
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    if not cloud_name:
        return False
        
    if not cloudinary.config().cloud_name:
        cloudinary.config(
            cloud_name = cloud_name,
            api_key = os.environ.get('CLOUDINARY_API_KEY'),
            api_secret = os.environ.get('CLOUDINARY_API_SECRET'),
            secure = True
        )
    return True

def upload_pickle_to_cloudinary(local_path, cloud_name):
    """
    Upload a local pickle file to Cloudinary as a raw file
    
    Args:
        local_path: Path to the local .pickle file
        cloud_name: Public ID to use in Cloudinary (e.g. 'CE_3')
    """
    try:
        if not init_cloudinary():
            logger.error("Cloudinary not configured. Skipping upload.")
            return None
            
        print(f"DEBUG: Syncing {cloud_name}.pickle to Cloudinary...")
        # Use resource_type='raw' for non-image files like .pickle
        response = cloudinary.uploader.upload(
            local_path, 
            public_id = cloud_name,
            folder = "facemarkpro/encodings",
            resource_type = "raw",
            overwrite = True,
            unique_filename = False
        )
        print(f"DEBUG: Successfully uploaded {cloud_name}.pickle")
        logger.info(f"Successfully uploaded {cloud_name}.pickle to Cloudinary: {response.get('secure_url')}")
        return response.get('secure_url')
    except Exception as e:
        print(f"DEBUG: Cloudinary upload failed: {e}")
        logger.error(f"Error uploading pickle to Cloudinary: {e}")
        return None

def upload_pickle_to_cloudinary_from_memory(data_dict, cloud_name):
    """
    Upload a dictionary to Cloudinary as a .pickle file directly from memory
    """
    try:
        if not init_cloudinary():
            return None
            
        print(f"DEBUG: Syncing {cloud_name}.pickle to Cloudinary from memory...")
        # Convert dict to pickle bytes
        pickle_bytes = pickle.dumps(data_dict)
        buffer = io.BytesIO(pickle_bytes)
        
        # Upload to Cloudinary
        response = cloudinary.uploader.upload(
            buffer,
            public_id = cloud_name,
            folder = "facemarkpro/encodings",
            resource_type = "raw",
            overwrite = True
        )
        print(f"DEBUG: Successfully uploaded {cloud_name}.pickle (memory)")
        return response.get('secure_url')
    except Exception as e:
        print(f"DEBUG: Cloudinary memory upload failed: {e}")
        logger.error(f"Error uploading pickle from memory: {e}")
        return None

def list_encodings_from_cloudinary():
    """
    List all pickle filenames in the facemarkpro/encodings folder
    """
    try:
        if not init_cloudinary():
            return []
            
        print("DEBUG: Listing encodings from Cloudinary...")
        # Use resources with prefix
        response = cloudinary.api.resources(
            type="upload",
            resource_type="raw",
            prefix="facemarkpro/encodings/"
        )
        resources = response.get('resources', [])
        filenames = []
        for res in resources:
            # res['public_id'] will be 'facemarkpro/encodings/BRANCH_SEM'
            public_id = res['public_id']
            filename = public_id.split('/')[-1]
            filenames.append(f"{filename}.pickle")
        return filenames
    except Exception as e:
        print(f"DEBUG: Cloudinary list failed: {e}")
        return []

def download_pickle_from_cloudinary(cloud_name, local_path):
    """
    Download a pickle file from Cloudinary if it exists
    
    Args:
        cloud_name: Public ID in Cloudinary (e.g. 'CE_3')
        local_path: Where to save the file locally
    """
    try:
        if not init_cloudinary():
            return False
            
        # Get the URL for the raw file
        print(f"DEBUG: Checking for {cloud_name}.pickle in Cloudinary...")
        try:
            # Use a faster check or direct URL if possible, or keep resource call
            resource = cloudinary.api.resource(f"facemarkpro/encodings/{cloud_name}", resource_type="raw")
            url = resource.get('secure_url')
        except Exception:
            print(f"DEBUG: {cloud_name}.pickle not found on cloud.")
            logger.info(f"Pickle {cloud_name} not found on Cloudinary")
            return False

        if not url:
            return False

        try:
            print(f"DEBUG: Downloading {cloud_name}.pickle...")
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, 'wb') as f:
                        f.write(response.read())
                    print(f"DEBUG: Successfully downloaded {cloud_name}.pickle")
                    logger.info(f"Successfully downloaded {cloud_name}.pickle from Cloudinary to {local_path}")
                    return True
                else:
                    logger.error(f"Failed to download pickle from Cloudinary, status code: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Network error downloading pickle: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error downloading pickle from Cloudinary: {e}")
        return False
def get_pickle_from_cloudinary(cloud_name):
    """
    Fetch pickle data directly from Cloudinary into memory
    """
    try:
        if not init_cloudinary():
            print("DEBUG: Cloudinary not initialized in get_pickle")
            return None
            
        print(f"DEBUG: Fetching {cloud_name} from cloud...")
        try:
            resource = cloudinary.api.resource(f"facemarkpro/encodings/{cloud_name}", resource_type="raw")
            url = resource.get('secure_url')
        except Exception as e:
            print(f"DEBUG: Cloudinary resource not found: {e}")
            return None

        if not url:
            print("DEBUG: No secure_url found in Cloudinary resource")
            return None

        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                data = pickle.loads(response.read())
                print(f"DEBUG: Successfully loaded {cloud_name} from cloud")
                return data
    except Exception as e:
        print(f"DEBUG: Error loading from Cloudinary: {e}")
        return None
    return None

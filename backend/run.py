from app import create_app
import os
import ssl

# Create the Flask app
app = create_app()

# Hugging Face Spaces compatibility
# The app will be served by Gradio/Streamlit wrapper or directly via Flask
if __name__ == "__main__":
    # Get port from environment variable (Hugging Face Spaces uses port 7860)
    port = int(os.environ.get("PORT", 7860))
    
    # Check if HTTPS is enabled via environment variable
    use_https = os.environ.get("USE_HTTPS", "false").lower() == "true"
    
    ssl_context = None
    if use_https:
        cert_file = "cert.pem"
        key_file = "key.pem"
        
        # Check if certificate files exist
        if os.path.exists(cert_file) and os.path.exists(key_file):
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(cert_file, key_file)
            print(f"[OK] HTTPS enabled on https://0.0.0.0:{port}")
            print(f"  Access via: https://localhost:{port} or https://192.168.1.3:{port}")
            print("  Note: You may need to accept the self-signed certificate warning in your browser")
        else:
            print("[WARN] HTTPS enabled but certificate files not found!")
            print(f"  Run: python generate_cert.py")
            print("  Falling back to HTTP...")
    else:
        print(f"[OK] HTTP mode on http://0.0.0.0:{port}")
        print(f"  Camera access only works on http://localhost:{port}")
        print("  To enable HTTPS for remote access, set USE_HTTPS=true in .env and run: python generate_cert.py")
    
    # Run the app
    # For Hugging Face Spaces, we need to bind to 0.0.0.0
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,  # Disable debug mode in production
        use_reloader=True,
        ssl_context=ssl_context
    )
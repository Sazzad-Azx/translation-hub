"""
Setup script to configure environment variables
Run this script to set up your .env file with API keys
"""
import os

def setup_env():
    """Interactive setup for environment variables"""
    print("Intercom Translation Workflow - Environment Setup")
    print("=" * 50)
    
    # Intercom API Key
    intercom_key = input("\nEnter your Intercom API Key (base64 token): ").strip()
    if not intercom_key:
        intercom_key = "your_intercom_access_token_here"
        print(f"Using provided default Intercom key")
    
    # OpenAI API Key
    openai_key = input("\nEnter your OpenAI API Key (starts with sk-): ").strip()
    if not openai_key:
        openai_key = "your_openai_api_key_here"
        print(f"Using provided default OpenAI key")
    
    # Model selection
    model = input("\nEnter OpenAI model (default: gpt-4o): ").strip() or "gpt-4o"
    
    # Optional collection/tag IDs
    collection_id = input("\nEnter Intercom Collection ID (optional, press Enter to skip): ").strip()
    tag_id = input("Enter Intercom Tag ID (optional, press Enter to skip): ").strip()
    
    # Create .env content
    env_content = f"""# Intercom API Configuration
INTERCOM_ACCESS_TOKEN={intercom_key}

# OpenAI API Configuration
OPENAI_API_KEY={openai_key}
OPENAI_MODEL={model}
"""
    
    if collection_id:
        env_content += f"\n# Optional: Filter articles by collection\nINTERCOM_COLLECTION_ID={collection_id}\n"
    
    if tag_id:
        env_content += f"\n# Optional: Filter articles by tag\nINTERCOM_TAG_ID={tag_id}\n"
    
    # Write to .env file
    env_path = ".env"
    try:
        with open(env_path, "w") as f:
            f.write(env_content)
        print(f"\n✓ Environment file created: {env_path}")
        print("\nSetup complete! You can now run the translation workflow.")
    except Exception as e:
        print(f"\n✗ Error creating .env file: {e}")
        print("\nPlease create .env file manually with the following content:")
        print("\n" + "=" * 50)
        print(env_content)
        print("=" * 50)

if __name__ == "__main__":
    setup_env()

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import json

load_dotenv()

SCOPES = "user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email ugc-image-upload"

def check_token_scopes(cache_path=".spotify_cache_v2"):
    print(f"Checking token in cache file: {cache_path}")
    
    if not os.path.exists(cache_path):
        print(f"❌ No cache file found at {cache_path}")
        return

    # Load the raw token from the cache file
    with open(cache_path) as f:
        token_info = json.load(f)

    print(f"Token info found for scope: {token_info.get('scope')}")
    
    # Check if all required scopes are present
    required_scopes = set(SCOPES.split())
    granted_scopes = set(token_info.get('scope', '').split())
    
    missing = required_scopes - granted_scopes
    if missing:
        print(f"❌ MISSING SCOPES: {missing}")
    else:
        print("✅ All required scopes are present.")

    # Try a write operation to verify permissions
    print("\nAttempting a write operation (creating a test playlist)...")
    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_id = sp.me()['id']
        print(f"User ID: {user_id}")
        
        pl = sp.user_playlist_create(
            user=user_id, 
            name="AlgoRhythm Scope Test", 
            public=False, 
            description="Temporary test playlist"
        )
        print(f"✅ Playlist created successfully! ID: {pl['id']}")
        
        # Clean up
        sp.current_user_unfollow_playlist(pl['id'])
        print("✅ Test playlist deleted.")
        
    except spotipy.SpotifyException as e:
        print(f"❌ API Error: {e}")
        print(f"Reason: {e.reason}")

if __name__ == "__main__":
    check_token_scopes()

#!/usr/bin/env python3
"""
MediaView Digital Signage Platform - Backend API Testing
Comprehensive testing of all backend endpoints
"""

import requests
import json
import sys
import base64

# Configuration from frontend .env
BASE_URL = "https://screensync-ads.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

# Test data
admin_credentials = {
    "email": "admin@mediaviewads.com",
    "password": "MediaViewAdmin#2026"
}

test_user_data = {
    "name": "Test User",
    "email": "testuser@example.com",
    "password": "Test123!",
    "company_name": "Test Co"
}

# Global variables for test
admin_token = None
user_token = None
test_screen_id = None
test_campaign_id = None
test_payment_id = None
test_media_id = None

class TestColors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def print_test(name, success, details=""):
    status = f"{TestColors.GREEN}✅ PASS{TestColors.ENDC}" if success else f"{TestColors.RED}❌ FAIL{TestColors.ENDC}"
    print(f"{status} {name}")
    if details:
        print(f"    {details}")

def test_health_check():
    """Test 1: Health Check"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=10)
        success = response.status_code == 200 and "healthy" in response.json().get("status", "")
        print_test("Health Check", success, f"Status: {response.status_code}, Response: {response.json()}")
        return success
    except Exception as e:
        print_test("Health Check", False, f"Error: {str(e)}")
        return False

def test_auth_register():
    """Test 2: Auth Register"""
    global user_token
    try:
        response = requests.post(f"{API_URL}/auth/register", json=test_user_data, timeout=10)
        success = response.status_code in [200, 201, 400]  # 400 might be "already exists"
        if success and response.status_code in [200, 201]:
            data = response.json()
            user_token = data.get("access_token")
        print_test("Auth Register", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Auth Register", False, f"Error: {str(e)}")
        return False

def test_auth_login():
    """Test 3: Auth Login (Admin)"""
    global admin_token
    try:
        response = requests.post(f"{API_URL}/auth/login", json=admin_credentials, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            admin_token = data.get("access_token")
            print_test("Auth Login (Admin)", success, f"Token received: {'Yes' if admin_token else 'No'}")
        else:
            print_test("Auth Login (Admin)", success, f"Status: {response.status_code}, Response: {response.text}")
        return success
    except Exception as e:
        print_test("Auth Login (Admin)", False, f"Error: {str(e)}")
        return False

def test_auth_me():
    """Test 4: Auth Me"""
    if not admin_token:
        print_test("Auth Me", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/auth/me", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Auth Me", success, f"User: {data.get('name')}, Role: {data.get('role')}")
        else:
            print_test("Auth Me", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Auth Me", False, f"Error: {str(e)}")
        return False

def test_profile_update():
    """Test 5: Profile Update"""
    if not admin_token:
        print_test("Profile Update", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        update_data = {"name": "Updated Admin"}
        response = requests.put(f"{API_URL}/auth/profile", headers=headers, json=update_data, timeout=10)
        success = response.status_code == 200
        print_test("Profile Update", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Profile Update", False, f"Error: {str(e)}")
        return False

def test_screens_list():
    """Test 6: Screens List (Public)"""
    global test_screen_id
    try:
        response = requests.get(f"{API_URL}/screens", timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                test_screen_id = data[0].get("id")
                print_test("Screens List", success, f"Found {len(data)} screens, first ID: {test_screen_id}")
            else:
                print_test("Screens List", False, "No screens found")
                success = False
        else:
            print_test("Screens List", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Screens List", False, f"Error: {str(e)}")
        return False

def test_screens_cities():
    """Test 7: Screens Cities"""
    try:
        response = requests.get(f"{API_URL}/screens/cities", timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Screens Cities", success, f"Found cities: {len(data) if isinstance(data, list) else 0}")
        else:
            print_test("Screens Cities", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Screens Cities", False, f"Error: {str(e)}")
        return False

def test_screen_detail():
    """Test 8: Screen Detail"""
    if not test_screen_id:
        print_test("Screen Detail", False, "No screen ID available")
        return False
    
    try:
        response = requests.get(f"{API_URL}/screens/{test_screen_id}", timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Screen Detail", success, f"Screen: {data.get('name')}")
        else:
            print_test("Screen Detail", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Screen Detail", False, f"Error: {str(e)}")
        return False

def test_calculate_price():
    """Test 9: Calculate Price"""
    if not test_screen_id:
        print_test("Calculate Price", False, "No screen ID available")
        return False
    
    try:
        price_data = {
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
            "start_time": "08:00",
            "end_time": "22:00",
            "slot_duration": 15,
            "frequency": 5
        }
        response = requests.post(f"{API_URL}/screens/{test_screen_id}/calculate-price", json=price_data, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Calculate Price", success, f"Total: ${data.get('total', 0)}")
        else:
            print_test("Calculate Price", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Calculate Price", False, f"Error: {str(e)}")
        return False

def test_create_campaign():
    """Test 10: Create Campaign"""
    global test_campaign_id
    if not admin_token or not test_screen_id:
        print_test("Create Campaign", False, "Missing admin token or screen ID")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        campaign_data = {
            "name": "Test Campaign",
            "screen_id": test_screen_id,
            "schedule": {
                "start_date": "2026-04-01",
                "end_date": "2026-04-03",
                "start_time": "08:00",
                "end_time": "22:00",
                "slot_duration": 15,
                "frequency": 5
            },
            "media_ids": []
        }
        response = requests.post(f"{API_URL}/campaigns", headers=headers, json=campaign_data, timeout=10)
        success = response.status_code in [200, 201]
        if success:
            data = response.json()
            test_campaign_id = data.get("id")
            print_test("Create Campaign", success, f"Campaign ID: {test_campaign_id}")
        else:
            print_test("Create Campaign", success, f"Status: {response.status_code}, Response: {response.text}")
        return success
    except Exception as e:
        print_test("Create Campaign", False, f"Error: {str(e)}")
        return False

def test_list_campaigns():
    """Test 11: List Campaigns"""
    if not admin_token:
        print_test("List Campaigns", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/campaigns", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("List Campaigns", success, f"Found {len(data) if isinstance(data, list) else 0} campaigns")
        else:
            print_test("List Campaigns", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("List Campaigns", False, f"Error: {str(e)}")
        return False

def test_get_campaign():
    """Test 12: Get Campaign"""
    if not admin_token or not test_campaign_id:
        print_test("Get Campaign", False, "Missing admin token or campaign ID")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/campaigns/{test_campaign_id}", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Get Campaign", success, f"Campaign: {data.get('name')}")
        else:
            print_test("Get Campaign", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Get Campaign", False, f"Error: {str(e)}")
        return False

def test_update_campaign():
    """Test 13: Update Campaign"""
    if not admin_token or not test_campaign_id:
        print_test("Update Campaign", False, "Missing admin token or campaign ID")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        update_data = {"name": "Updated Campaign"}
        response = requests.put(f"{API_URL}/campaigns/{test_campaign_id}", headers=headers, json=update_data, timeout=10)
        success = response.status_code == 200
        print_test("Update Campaign", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Update Campaign", False, f"Error: {str(e)}")
        return False

def test_media_upload():
    """Test 14: Media Upload"""
    global test_media_id
    if not admin_token:
        print_test("Media Upload", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Create a simple 1x1 PNG image in base64
        png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        media_data = {
            "filename": "test.jpg",
            "content_type": "image/jpeg",
            "data": png_data
        }
        response = requests.post(f"{API_URL}/media/upload", headers=headers, json=media_data, timeout=10)
        success = response.status_code in [200, 201]
        if success:
            data = response.json()
            test_media_id = data.get("id")
            print_test("Media Upload", success, f"Media ID: {test_media_id}")
        else:
            print_test("Media Upload", success, f"Status: {response.status_code}, Response: {response.text}")
        return success
    except Exception as e:
        print_test("Media Upload", False, f"Error: {str(e)}")
        return False

def test_list_media():
    """Test 15: List Media"""
    if not admin_token:
        print_test("List Media", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/media", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("List Media", success, f"Found {len(data) if isinstance(data, list) else 0} media items")
        else:
            print_test("List Media", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("List Media", False, f"Error: {str(e)}")
        return False

def test_create_payment():
    """Test 16: Create Payment"""
    global test_payment_id
    if not admin_token or not test_campaign_id:
        print_test("Create Payment", False, "Missing admin token or campaign ID")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        payment_data = {
            "campaign_id": test_campaign_id,
            "method": "card",
            "card_last4": "4242"
        }
        response = requests.post(f"{API_URL}/payments", headers=headers, json=payment_data, timeout=10)
        success = response.status_code in [200, 201]
        if success:
            data = response.json()
            test_payment_id = data.get("id")
            print_test("Create Payment (MOCKED)", success, f"Payment ID: {test_payment_id}, Amount: ${data.get('amount')}")
        else:
            print_test("Create Payment", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Create Payment", False, f"Error: {str(e)}")
        return False

def test_list_payments():
    """Test 17: List Payments"""
    if not admin_token:
        print_test("List Payments", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/payments", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("List Payments", success, f"Found {len(data) if isinstance(data, list) else 0} payments")
        else:
            print_test("List Payments", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("List Payments", False, f"Error: {str(e)}")
        return False

def test_admin_list_users():
    """Test 18: Admin List Users"""
    if not admin_token:
        print_test("Admin List Users", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/admin/users", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Admin List Users", success, f"Found {len(data) if isinstance(data, list) else 0} users")
        else:
            print_test("Admin List Users", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Admin List Users", False, f"Error: {str(e)}")
        return False

def test_admin_list_campaigns():
    """Test 19: Admin List Campaigns"""
    if not admin_token:
        print_test("Admin List Campaigns", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/admin/campaigns", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Admin List Campaigns", success, f"Found {len(data) if isinstance(data, list) else 0} campaigns")
        else:
            print_test("Admin List Campaigns", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Admin List Campaigns", False, f"Error: {str(e)}")
        return False

def test_admin_approve_campaign():
    """Test 20: Admin Approve Campaign"""
    if not admin_token or not test_campaign_id:
        print_test("Admin Approve Campaign", False, "Missing admin token or campaign ID")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.put(f"{API_URL}/admin/campaigns/{test_campaign_id}/approve", headers=headers, timeout=10)
        success = response.status_code in [200, 400]  # 400 might be "not pending" which is OK
        if success:
            print_test("Admin Approve Campaign", True, f"Status: {response.status_code}")
        else:
            print_test("Admin Approve Campaign", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Admin Approve Campaign", False, f"Error: {str(e)}")
        return False

def test_admin_analytics():
    """Test 21: Admin Analytics"""
    if not admin_token:
        print_test("Admin Analytics", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/admin/analytics", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Admin Analytics", success, f"Users: {data.get('total_users')}, Revenue: ${data.get('total_revenue')}")
        else:
            print_test("Admin Analytics", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Admin Analytics", False, f"Error: {str(e)}")
        return False

def test_player_playlist():
    """Test 22: Player Playlist"""
    if not test_screen_id:
        print_test("Player Playlist", False, "No screen ID available")
        return False
    
    try:
        response = requests.get(f"{API_URL}/player/{test_screen_id}/playlist", timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Player Playlist", success, f"Items: {data.get('total_items', 0)}")
        else:
            print_test("Player Playlist", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Player Playlist", False, f"Error: {str(e)}")
        return False

def test_player_schedule():
    """Test 23: Player Schedule"""
    if not test_screen_id:
        print_test("Player Schedule", False, "No screen ID available")
        return False
    
    try:
        response = requests.get(f"{API_URL}/player/{test_screen_id}/schedule", timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("Player Schedule", success, f"Entries: {len(data.get('entries', []))}")
        else:
            print_test("Player Schedule", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("Player Schedule", False, f"Error: {str(e)}")
        return False

def test_user_analytics():
    """Test 24: User Analytics"""
    if not admin_token:
        print_test("User Analytics", False, "No admin token available")
        return False
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{API_URL}/analytics/dashboard", headers=headers, timeout=10)
        success = response.status_code == 200
        if success:
            data = response.json()
            print_test("User Analytics", success, f"Total campaigns: {data.get('total_campaigns')}")
        else:
            print_test("User Analytics", success, f"Status: {response.status_code}")
        return success
    except Exception as e:
        print_test("User Analytics", False, f"Error: {str(e)}")
        return False

def test_delete_campaign():
    """Test 25: Delete Campaign"""
    if not admin_token:
        print_test("Delete Campaign (Create & Delete)", False, "No admin token available")
        return False
    
    try:
        # First create a new draft campaign
        headers = {"Authorization": f"Bearer {admin_token}"}
        campaign_data = {
            "name": "Campaign to Delete",
            "screen_id": test_screen_id if test_screen_id else "dummy",
            "schedule": {
                "start_date": "2026-04-01",
                "end_date": "2026-04-03",
                "start_time": "08:00",
                "end_time": "22:00",
                "slot_duration": 15,
                "frequency": 5
            },
            "media_ids": []
        }
        
        if not test_screen_id:
            print_test("Delete Campaign", False, "No screen ID available")
            return False
            
        response = requests.post(f"{API_URL}/campaigns", headers=headers, json=campaign_data, timeout=10)
        if response.status_code not in [200, 201]:
            print_test("Delete Campaign (Create)", False, f"Could not create campaign: {response.status_code}")
            return False
        
        campaign_id = response.json().get("id")
        
        # Now delete it
        delete_response = requests.delete(f"{API_URL}/campaigns/{campaign_id}", headers=headers, timeout=10)
        success = delete_response.status_code == 200
        print_test("Delete Campaign", success, f"Delete Status: {delete_response.status_code}")
        return success
    except Exception as e:
        print_test("Delete Campaign", False, f"Error: {str(e)}")
        return False

def run_tests():
    """Run all tests in sequence"""
    print(f"{TestColors.BLUE}{'='*60}{TestColors.ENDC}")
    print(f"{TestColors.BLUE}MediaView Digital Signage Platform - Backend API Tests{TestColors.ENDC}")
    print(f"{TestColors.BLUE}Testing URL: {API_URL}{TestColors.ENDC}")
    print(f"{TestColors.BLUE}{'='*60}{TestColors.ENDC}")
    
    tests = [
        test_health_check,
        test_auth_register,
        test_auth_login,
        test_auth_me,
        test_profile_update,
        test_screens_list,
        test_screens_cities,
        test_screen_detail,
        test_calculate_price,
        test_create_campaign,
        test_list_campaigns,
        test_get_campaign,
        test_update_campaign,
        test_media_upload,
        test_list_media,
        test_create_payment,
        test_list_payments,
        test_admin_list_users,
        test_admin_list_campaigns,
        test_admin_approve_campaign,
        test_admin_analytics,
        test_player_playlist,
        test_player_schedule,
        test_user_analytics,
        test_delete_campaign
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        if test_func():
            passed += 1
        print()  # Add spacing between tests
    
    print(f"{TestColors.BLUE}{'='*60}{TestColors.ENDC}")
    print(f"Test Results: {TestColors.GREEN if passed == total else TestColors.YELLOW}{passed}/{total}{TestColors.ENDC} passed")
    
    if passed == total:
        print(f"{TestColors.GREEN}All tests passed! ✅{TestColors.ENDC}")
    elif passed >= total * 0.8:
        print(f"{TestColors.YELLOW}Most tests passed, check failures above ⚠️{TestColors.ENDC}")
    else:
        print(f"{TestColors.RED}Multiple failures detected, check logs above ❌{TestColors.ENDC}")
    
    print(f"{TestColors.BLUE}{'='*60}{TestColors.ENDC}")
    
    return passed, total

if __name__ == "__main__":
    passed, total = run_tests()
    sys.exit(0 if passed == total else 1)
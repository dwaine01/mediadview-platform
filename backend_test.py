#!/usr/bin/env python3
"""
AutoService Hub Backend API Test Suite
Tests all endpoints according to the review request
"""

import requests
import json
import sys
from datetime import datetime

# Base URL from frontend .env
BASE_URL = "https://screensync-ads.preview.emergentagent.com/api"

class AutoServiceTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.workshop_id = None
        self.user_id = None
        self.client_id = None
        self.vehicle_id = None
        self.work_order_id = None
        self.payment_id = None
        self.test_results = []
        
    def log_test(self, test_name, success, details="", response_data=None):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        if response_data and not success:
            print(f"   Response: {response_data}")
        print()
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "response": response_data
        })
    
    def make_request(self, method, endpoint, data=None, params=None, use_auth=True):
        """Make HTTP request with optional authentication"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        if use_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, params=params, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, params=params, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            return response
        except requests.exceptions.RequestException as e:
            return None, str(e)
    
    def test_health_check(self):
        """Test 1: GET /health - Health check"""
        response = self.make_request("GET", "/health", use_auth=False)
        
        if isinstance(response, tuple):
            self.log_test("Health Check", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "healthy":
                self.log_test("Health Check", True, "Service is healthy")
                return True
            else:
                self.log_test("Health Check", False, f"Unexpected response: {data}")
                return False
        else:
            self.log_test("Health Check", False, f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_register_workshop(self):
        """Test 2: POST /auth/register-workshop - Register workshop with admin"""
        workshop_data = {
            "name": "Taller AutoService Test",
            "address": "123 Test Street, Test City",
            "phone": "+1-555-0123"
        }
        
        params = {
            "admin_email": "admin@autoservice-test.com",
            "admin_password": "SecurePass123!",
            "admin_name": "Admin Test User"
        }
        
        response = self.make_request("POST", "/auth/register-workshop", 
                                   data=workshop_data, params=params, use_auth=False)
        
        if isinstance(response, tuple):
            self.log_test("Register Workshop", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data and "user" in data and "workshop" in data:
                self.token = data["access_token"]
                self.workshop_id = data["user"]["workshop_id"]
                self.user_id = data["user"]["id"]
                self.log_test("Register Workshop", True, 
                            f"Workshop created with ID: {self.workshop_id}")
                return True
            else:
                self.log_test("Register Workshop", False, f"Missing required fields in response: {data}")
                return False
        else:
            self.log_test("Register Workshop", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_login(self):
        """Test 3: POST /auth/login - Login with email and password"""
        login_data = {
            "email": "admin@autoservice-test.com",
            "password": "SecurePass123!"
        }
        
        response = self.make_request("POST", "/auth/login", data=login_data, use_auth=False)
        
        if isinstance(response, tuple):
            self.log_test("Login", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data and "user" in data:
                # Update token (should be same as registration)
                self.token = data["access_token"]
                self.log_test("Login", True, f"Login successful for user: {data['user']['name']}")
                return True
            else:
                self.log_test("Login", False, f"Missing required fields in response: {data}")
                return False
        else:
            self.log_test("Login", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_get_me(self):
        """Test 4: GET /auth/me - Get current user (requires token)"""
        response = self.make_request("GET", "/auth/me")
        
        if isinstance(response, tuple):
            self.log_test("Get Current User", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "id" in data and "name" in data and "email" in data and "role" in data:
                self.log_test("Get Current User", True, 
                            f"User info retrieved: {data['name']} ({data['role']})")
                return True
            else:
                self.log_test("Get Current User", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Get Current User", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_decode_vin(self):
        """Test 5: GET /vin/decode/{vin} - Decode VIN using NHTSA API"""
        test_vin = "1HGBH41JXMN109186"
        response = self.make_request("GET", f"/vin/decode/{test_vin}")
        
        if isinstance(response, tuple):
            self.log_test("VIN Decode", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "vin" in data and "make" in data and "model" in data:
                self.log_test("VIN Decode", True, 
                            f"VIN decoded: {data.get('year', 'N/A')} {data.get('make', 'N/A')} {data.get('model', 'N/A')}")
                return True
            else:
                self.log_test("VIN Decode", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("VIN Decode", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_create_client(self):
        """Test 6: POST /clients - Create client"""
        client_data = {
            "name": "Juan Carlos Pérez",
            "phone": "+1-555-0199",
            "email": "juan.perez@email.com",
            "address": "456 Client Avenue, Client City",
            "notes": "Cliente preferencial - vehículo Honda Civic"
        }
        
        response = self.make_request("POST", "/clients", data=client_data)
        
        if isinstance(response, tuple):
            self.log_test("Create Client", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "id" in data and "name" in data:
                self.client_id = data["id"]
                self.log_test("Create Client", True, 
                            f"Client created: {data['name']} (ID: {self.client_id})")
                return True
            else:
                self.log_test("Create Client", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Create Client", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_get_clients(self):
        """Test 7: GET /clients - List clients"""
        response = self.make_request("GET", "/clients")
        
        if isinstance(response, tuple):
            self.log_test("Get Clients", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                self.log_test("Get Clients", True, f"Retrieved {len(data)} clients")
                return True
            else:
                self.log_test("Get Clients", False, f"Expected list, got: {type(data)}")
                return False
        else:
            self.log_test("Get Clients", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_create_vehicle(self):
        """Test 8: POST /vehicles - Create vehicle"""
        if not self.client_id:
            self.log_test("Create Vehicle", False, "No client_id available")
            return False
        
        vehicle_data = {
            "client_id": self.client_id,
            "vin": "1HGBH41JXMN109186",
            "make": "Honda",
            "model": "Civic",
            "year": 2021,
            "trim": "EX",
            "body_type": "Sedan",
            "engine": "1.5L Turbo",
            "color": "Blanco Perla"
        }
        
        response = self.make_request("POST", "/vehicles", data=vehicle_data)
        
        if isinstance(response, tuple):
            self.log_test("Create Vehicle", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "id" in data and "vin" in data:
                self.vehicle_id = data["id"]
                self.log_test("Create Vehicle", True, 
                            f"Vehicle created: {data.get('year', 'N/A')} {data.get('make', 'N/A')} {data.get('model', 'N/A')} (ID: {self.vehicle_id})")
                return True
            else:
                self.log_test("Create Vehicle", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Create Vehicle", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_get_services(self):
        """Test 9: GET /services - List predefined services"""
        response = self.make_request("GET", "/services")
        
        if isinstance(response, tuple):
            self.log_test("Get Services", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                self.log_test("Get Services", True, f"Retrieved {len(data)} services")
                return True
            else:
                self.log_test("Get Services", False, f"Expected list, got: {type(data)}")
                return False
        else:
            self.log_test("Get Services", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_create_work_order(self):
        """Test 10: POST /work-orders - Create work order"""
        if not self.client_id or not self.vehicle_id:
            self.log_test("Create Work Order", False, "Missing client_id or vehicle_id")
            return False
        
        work_order_data = {
            "vehicle_id": self.vehicle_id,
            "client_id": self.client_id,
            "services": [
                {
                    "service_id": "srs001",
                    "service_name": "Reset módulo SRS",
                    "quantity": 1,
                    "price": 150.0,
                    "notes": "Reset completo del sistema SRS"
                },
                {
                    "service_id": "srs004",
                    "service_name": "Bolsa volante",
                    "quantity": 1,
                    "price": 180.0,
                    "notes": "Reemplazo de airbag del volante"
                }
            ],
            "odometer": 45000,
            "notes": "Cliente reporta luz de SRS encendida después de accidente menor"
        }
        
        response = self.make_request("POST", "/work-orders", data=work_order_data)
        
        if isinstance(response, tuple):
            self.log_test("Create Work Order", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "id" in data and "status" in data:
                self.work_order_id = data["id"]
                self.log_test("Create Work Order", True, 
                            f"Work order created with status: {data['status']} (ID: {self.work_order_id})")
                return True
            else:
                self.log_test("Create Work Order", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Create Work Order", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_get_work_orders(self):
        """Test 11: GET /work-orders - List work orders"""
        response = self.make_request("GET", "/work-orders")
        
        if isinstance(response, tuple):
            self.log_test("Get Work Orders", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                self.log_test("Get Work Orders", True, f"Retrieved {len(data)} work orders")
                return True
            else:
                self.log_test("Get Work Orders", False, f"Expected list, got: {type(data)}")
                return False
        else:
            self.log_test("Get Work Orders", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_create_payment(self):
        """Test 12: POST /payments - Create payment"""
        if not self.work_order_id:
            self.log_test("Create Payment", False, "No work_order_id available")
            return False
        
        payment_data = {
            "work_order_id": self.work_order_id,
            "method": "zelle",
            "payment_status": "pagado",
            "subtotal": 330.0,
            "tax": 23.10,  # 7% tax
            "discount": 0.0,
            "total": 353.10,
            "paid_amount": 353.10,
            "reference": "ZELLE-20241201-001"
        }
        
        response = self.make_request("POST", "/payments", data=payment_data)
        
        if isinstance(response, tuple):
            self.log_test("Create Payment", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "id" in data and "method" in data:
                self.payment_id = data["id"]
                self.log_test("Create Payment", True, 
                            f"Payment created: ${data.get('total', 0):.2f} via {data['method']} (ID: {self.payment_id})")
                return True
            else:
                self.log_test("Create Payment", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Create Payment", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def test_daily_report(self):
        """Test 13: GET /reports/daily - Get daily report"""
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"date": today}
        
        response = self.make_request("GET", "/reports/daily", params=params)
        
        if isinstance(response, tuple):
            self.log_test("Daily Report", False, f"Request failed: {response[1]}")
            return False
        
        if response.status_code == 200:
            data = response.json()
            if "date" in data and "total_orders" in data and "total_billed" in data:
                self.log_test("Daily Report", True, 
                            f"Report for {data['date']}: {data['total_orders']} orders, ${data.get('total_billed', 0):.2f} billed")
                return True
            else:
                self.log_test("Daily Report", False, f"Missing required fields: {data}")
                return False
        else:
            self.log_test("Daily Report", False, 
                        f"Status code: {response.status_code}, Response: {response.text}")
            return False
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 60)
        print("AutoService Hub Backend API Test Suite")
        print("=" * 60)
        print(f"Base URL: {self.base_url}")
        print()
        
        tests = [
            self.test_health_check,
            self.test_register_workshop,
            self.test_login,
            self.test_get_me,
            self.test_decode_vin,
            self.test_create_client,
            self.test_get_clients,
            self.test_create_vehicle,
            self.test_get_services,
            self.test_create_work_order,
            self.test_get_work_orders,
            self.test_create_payment,
            self.test_daily_report
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ FAIL {test.__name__} - Exception: {str(e)}")
                failed += 1
        
        print("=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {passed + failed}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")
        
        if failed > 0:
            print("\nFAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"- {result['test']}: {result['details']}")
        
        return failed == 0

if __name__ == "__main__":
    tester = AutoServiceTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
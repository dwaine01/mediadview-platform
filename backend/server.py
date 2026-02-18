from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import jwt
import bcrypt
import httpx
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Helper function to convert MongoDB documents
def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                result['_id'] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [serialize_doc(v) if isinstance(v, dict) else v for v in value]
            else:
                result[key] = value
        return result
    return doc

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'autoservice_db')]

# JWT Settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'autoservice-secret-key-2024')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer()

# Create the main app
app = FastAPI(title="AutoService Hub API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============ MODELS ============

class UserBase(BaseModel):
    name: str
    email: str
    role: str = "tech"  # admin or tech
    workshop_id: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class Workshop(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    tax_rate: float = 7.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WorkshopCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None

class Client(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class Vehicle(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    client_id: str
    vin: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    trim: Optional[str] = None
    body_type: Optional[str] = None
    engine: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class VehicleCreate(BaseModel):
    client_id: str
    vin: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    trim: Optional[str] = None
    body_type: Optional[str] = None
    engine: Optional[str] = None
    color: Optional[str] = None

class ServiceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    code: str
    name: str
    category: str  # srs, cinturones, adas
    default_price: float = 0.0
    active: bool = True

class ServiceItemCreate(BaseModel):
    code: str
    name: str
    category: str
    default_price: float = 0.0

class WorkOrderService(BaseModel):
    service_id: str
    service_name: str
    quantity: int = 1
    price: float
    side: Optional[str] = None  # left, right, both
    notes: Optional[str] = None

class WorkOrder(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    vehicle_id: str
    client_id: str
    tech_id: str
    status: str = "iniciado"  # iniciado, pendiente, terminado
    services: List[WorkOrderService] = []
    odometer: Optional[int] = None
    notes: Optional[str] = None
    photos_before: List[str] = []
    photos_after: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class WorkOrderCreate(BaseModel):
    vehicle_id: str
    client_id: str
    tech_id: Optional[str] = None  # Admin can assign to specific tech
    services: List[WorkOrderService] = []
    odometer: Optional[int] = None
    notes: Optional[str] = None

class WorkOrderUpdate(BaseModel):
    status: Optional[str] = None
    tech_id: Optional[str] = None  # Admin can reassign
    services: Optional[List[WorkOrderService]] = None
    odometer: Optional[int] = None
    notes: Optional[str] = None
    photos_before: Optional[List[str]] = None
    photos_after: Optional[List[str]] = None

class Payment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workshop_id: str
    work_order_id: str
    method: str  # zelle, cash, check, other
    payment_status: str = "pendiente"  # pagado, pendiente
    subtotal: float = 0.0
    tax: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    paid_amount: float = 0.0
    reference: Optional[str] = None
    receipt_photo: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PaymentCreate(BaseModel):
    work_order_id: str
    method: str
    payment_status: str = "pendiente"
    subtotal: float = 0.0
    tax: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    paid_amount: float = 0.0
    reference: Optional[str] = None
    receipt_photo: Optional[str] = None

class PaymentUpdate(BaseModel):
    method: Optional[str] = None
    payment_status: Optional[str] = None
    paid_amount: Optional[float] = None
    reference: Optional[str] = None
    receipt_photo: Optional[str] = None

# ============ AUTH HELPERS ============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str, workshop_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "workshop_id": workshop_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

# ============ ROUTES ============

@api_router.get("/")
async def root():
    return {"message": "AutoService Hub API", "version": "1.0.0"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# ============ AUTH ROUTES ============

@api_router.post("/auth/register-workshop")
async def register_workshop(workshop: WorkshopCreate, admin_email: str, admin_password: str, admin_name: str):
    """Register a new workshop with admin user"""
    # Check if email exists
    existing = await db.users.find_one({"email": admin_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    # Create workshop
    workshop_obj = Workshop(**workshop.dict())
    await db.workshops.insert_one(workshop_obj.dict())
    
    # Create admin user
    user_obj = User(
        name=admin_name,
        email=admin_email,
        role="admin",
        workshop_id=workshop_obj.id
    )
    user_dict = user_obj.dict()
    user_dict["password_hash"] = hash_password(admin_password)
    await db.users.insert_one(user_dict)
    
    # Create default services
    default_services = [
        {"code": "SRS001", "name": "Reset módulo SRS", "category": "srs", "default_price": 150.0},
        {"code": "SRS002", "name": "Bolsa techo izquierda", "category": "srs", "default_price": 200.0},
        {"code": "SRS003", "name": "Bolsa techo derecha", "category": "srs", "default_price": 200.0},
        {"code": "SRS004", "name": "Bolsa volante", "category": "srs", "default_price": 180.0},
        {"code": "SRS005", "name": "Bolsa asiento izquierdo", "category": "srs", "default_price": 175.0},
        {"code": "SRS006", "name": "Bolsa asiento derecho", "category": "srs", "default_price": 175.0},
        {"code": "SRS007", "name": "Knee airbag izquierdo", "category": "srs", "default_price": 160.0},
        {"code": "SRS008", "name": "Knee airbag derecho", "category": "srs", "default_price": 160.0},
        {"code": "SRS009", "name": "Pretensioner izquierdo", "category": "srs", "default_price": 120.0},
        {"code": "SRS010", "name": "Pretensioner derecho", "category": "srs", "default_price": 120.0},
        {"code": "SRS011", "name": "Sensor ocupante", "category": "srs", "default_price": 140.0},
        {"code": "BELT001", "name": "Reparación cinturón", "category": "cinturones", "default_price": 85.0},
        {"code": "BELT002", "name": "Reemplazo cinturón", "category": "cinturones", "default_price": 250.0},
        {"code": "ADAS001", "name": "Calibración radar frontal", "category": "adas", "default_price": 300.0},
        {"code": "ADAS002", "name": "Calibración cámara", "category": "adas", "default_price": 280.0},
    ]
    
    for service in default_services:
        service_obj = ServiceItem(workshop_id=workshop_obj.id, **service)
        await db.services.insert_one(service_obj.dict())
    
    token = create_token(user_obj.id, workshop_obj.id, "admin")
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_obj.id,
            "name": user_obj.name,
            "email": admin_email,
            "role": "admin",
            "workshop_id": workshop_obj.id
        },
        "workshop": workshop_obj.dict()
    }

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    if not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    if not user.get("active", True):
        raise HTTPException(status_code=401, detail="Usuario desactivado")
    
    token = create_token(user["id"], user["workshop_id"], user["role"])
    
    return TokenResponse(
        access_token=token,
        user={
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "workshop_id": user["workshop_id"]
        }
    )

@api_router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "name": current_user["name"],
        "email": current_user["email"],
        "role": current_user["role"],
        "workshop_id": current_user["workshop_id"]
    }

# ============ USER ROUTES (Admin only) ============

@api_router.post("/users")
async def create_user(user_data: UserCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede crear usuarios")
    
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    user_obj = User(
        name=user_data.name,
        email=user_data.email,
        role=user_data.role,
        workshop_id=current_user["workshop_id"]
    )
    user_dict = user_obj.dict()
    user_dict["password_hash"] = hash_password(user_data.password)
    await db.users.insert_one(user_dict)
    
    return {
        "id": user_obj.id,
        "name": user_obj.name,
        "email": user_obj.email,
        "role": user_obj.role,
        "active": user_obj.active
    }

@api_router.get("/users")
async def get_users(current_user: dict = Depends(get_current_user)):
    users = await db.users.find({"workshop_id": current_user["workshop_id"]}).to_list(100)
    return [{
        "id": u["id"],
        "name": u["name"],
        "email": u["email"],
        "role": u["role"],
        "active": u.get("active", True)
    } for u in users]

@api_router.put("/users/{user_id}")
async def update_user(user_id: str, active: bool, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede modificar usuarios")
    
    result = await db.users.update_one(
        {"id": user_id, "workshop_id": current_user["workshop_id"]},
        {"$set": {"active": active}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {"message": "Usuario actualizado"}

# ============ VIN DECODE ============

@api_router.get("/vin/decode/{vin}")
async def decode_vin(vin: str, current_user: dict = Depends(get_current_user)):
    # Validate VIN
    vin = vin.upper().strip()
    if len(vin) != 17:
        raise HTTPException(status_code=400, detail="VIN debe tener 17 caracteres")
    
    invalid_chars = ['I', 'O', 'Q']
    for char in invalid_chars:
        if char in vin:
            raise HTTPException(status_code=400, detail=f"VIN no puede contener '{char}'")
    
    # Call NHTSA API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json",
                timeout=10.0
            )
            data = response.json()
            
            if data.get("Results") and len(data["Results"]) > 0:
                result = data["Results"][0]
                return {
                    "vin": vin,
                    "make": result.get("Make", ""),
                    "model": result.get("Model", ""),
                    "year": int(result.get("ModelYear", 0)) if result.get("ModelYear") else None,
                    "trim": result.get("Trim", ""),
                    "body_type": result.get("BodyClass", ""),
                    "engine": f"{result.get('EngineConfiguration', '')} {result.get('DisplacementL', '')}L".strip(),
                    "vehicle_type": result.get("VehicleType", ""),
                    "plant_country": result.get("PlantCountry", "")
                }
            else:
                raise HTTPException(status_code=404, detail="No se pudo decodificar el VIN")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout al consultar NHTSA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al decodificar VIN: {str(e)}")

# ============ CLIENT ROUTES ============

@api_router.post("/clients")
async def create_client(client_data: ClientCreate, current_user: dict = Depends(get_current_user)):
    client_obj = Client(
        workshop_id=current_user["workshop_id"],
        **client_data.dict()
    )
    await db.clients.insert_one(client_obj.dict())
    return client_obj.dict()

@api_router.get("/clients")
async def get_clients(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"workshop_id": current_user["workshop_id"]}
    
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    
    clients = await db.clients.find(query).to_list(100)
    return serialize_doc(clients)

@api_router.get("/clients/{client_id}")
async def get_client(client_id: str, current_user: dict = Depends(get_current_user)):
    client = await db.clients.find_one({
        "id": client_id,
        "workshop_id": current_user["workshop_id"]
    })
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return serialize_doc(client)

@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, client_data: ClientCreate, current_user: dict = Depends(get_current_user)):
    result = await db.clients.update_one(
        {"id": client_id, "workshop_id": current_user["workshop_id"]},
        {"$set": client_data.dict()}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente actualizado"}

# ============ VEHICLE ROUTES ============

@api_router.post("/vehicles")
async def create_vehicle(vehicle_data: VehicleCreate, current_user: dict = Depends(get_current_user)):
    vehicle_obj = Vehicle(
        workshop_id=current_user["workshop_id"],
        **vehicle_data.dict()
    )
    await db.vehicles.insert_one(vehicle_obj.dict())
    return vehicle_obj.dict()

@api_router.get("/vehicles")
async def get_vehicles(client_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"workshop_id": current_user["workshop_id"]}
    if client_id:
        query["client_id"] = client_id
    
    vehicles = await db.vehicles.find(query).to_list(100)
    return serialize_doc(vehicles)

@api_router.get("/vehicles/by-vin/{vin}")
async def get_vehicle_by_vin(vin: str, current_user: dict = Depends(get_current_user)):
    vehicle = await db.vehicles.find_one({
        "vin": vin.upper(),
        "workshop_id": current_user["workshop_id"]
    })
    return serialize_doc(vehicle)

# ============ SERVICE ROUTES ============

@api_router.get("/services")
async def get_services(category: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    query = {"workshop_id": current_user["workshop_id"], "active": True}
    if category:
        query["category"] = category
    
    services = await db.services.find(query).to_list(100)
    return serialize_doc(services)

@api_router.post("/services")
async def create_service(service_data: ServiceItemCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede crear servicios")
    
    service_obj = ServiceItem(
        workshop_id=current_user["workshop_id"],
        **service_data.dict()
    )
    await db.services.insert_one(service_obj.dict())
    return service_obj.dict()

@api_router.put("/services/{service_id}")
async def update_service(service_id: str, service_data: ServiceItemCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede modificar servicios")
    
    result = await db.services.update_one(
        {"id": service_id, "workshop_id": current_user["workshop_id"]},
        {"$set": service_data.dict()}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return {"message": "Servicio actualizado"}

# ============ WORK ORDER ROUTES ============

@api_router.post("/work-orders")
async def create_work_order(order_data: WorkOrderCreate, current_user: dict = Depends(get_current_user)):
    order_obj = WorkOrder(
        workshop_id=current_user["workshop_id"],
        tech_id=current_user["id"],
        started_at=datetime.utcnow(),
        **order_data.dict()
    )
    await db.work_orders.insert_one(order_obj.dict())
    return order_obj.dict()

@api_router.get("/work-orders")
async def get_work_orders(
    status: Optional[str] = None,
    tech_id: Optional[str] = None,
    date: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {"workshop_id": current_user["workshop_id"]}
    
    if status:
        query["status"] = status
    
    if tech_id:
        query["tech_id"] = tech_id
    elif current_user["role"] != "admin":
        query["tech_id"] = current_user["id"]
    
    if date:
        # Parse date and filter by day
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d")
            next_day = filter_date + timedelta(days=1)
            query["created_at"] = {"$gte": filter_date, "$lt": next_day}
        except ValueError:
            pass
    
    orders = await db.work_orders.find(query).sort("created_at", -1).to_list(100)
    
    # Convert ObjectId to string for JSON serialization
    for order in orders:
        if "_id" in order:
            order["_id"] = str(order["_id"])
    
    # Enrich with vehicle and client info
    enriched_orders = []
    for order in orders:
        vehicle = await db.vehicles.find_one({"id": order["vehicle_id"]})
        client = await db.clients.find_one({"id": order["client_id"]})
        tech = await db.users.find_one({"id": order["tech_id"]})
        payment = await db.payments.find_one({"work_order_id": order["id"]})
        
        # Convert ObjectId to string for nested objects
        if vehicle and "_id" in vehicle:
            vehicle["_id"] = str(vehicle["_id"])
        if client and "_id" in client:
            client["_id"] = str(client["_id"])
        if tech and "_id" in tech:
            tech["_id"] = str(tech["_id"])
        if payment and "_id" in payment:
            payment["_id"] = str(payment["_id"])
        
        order["vehicle"] = vehicle
        order["client"] = client
        order["tech_name"] = tech["name"] if tech else "Desconocido"
        order["payment"] = payment
        enriched_orders.append(order)
    
    return enriched_orders

@api_router.get("/work-orders/{order_id}")
async def get_work_order(order_id: str, current_user: dict = Depends(get_current_user)):
    order = await db.work_orders.find_one({
        "id": order_id,
        "workshop_id": current_user["workshop_id"]
    })
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    vehicle = await db.vehicles.find_one({"id": order["vehicle_id"]})
    client = await db.clients.find_one({"id": order["client_id"]})
    tech = await db.users.find_one({"id": order["tech_id"]})
    payment = await db.payments.find_one({"work_order_id": order["id"]})
    
    order["vehicle"] = serialize_doc(vehicle)
    order["client"] = serialize_doc(client)
    order["tech_name"] = tech["name"] if tech else "Desconocido"
    order["payment"] = serialize_doc(payment)
    
    return serialize_doc(order)

@api_router.put("/work-orders/{order_id}")
async def update_work_order(order_id: str, order_data: WorkOrderUpdate, current_user: dict = Depends(get_current_user)):
    # Get current order to check status
    current_order = await db.work_orders.find_one({
        "id": order_id,
        "workshop_id": current_user["workshop_id"]
    })
    
    if not current_order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    
    update_dict = {k: v for k, v in order_data.dict().items() if v is not None}
    
    # Status change validation
    if "status" in update_dict:
        current_status = current_order.get("status", "iniciado")
        new_status = update_dict["status"]
        
        # Define status order
        status_order = {"iniciado": 0, "pendiente": 1, "terminado": 2}
        
        # If not admin, only allow forward progression
        if current_user["role"] != "admin":
            if status_order.get(new_status, 0) < status_order.get(current_status, 0):
                raise HTTPException(
                    status_code=403, 
                    detail="Solo el administrador puede revertir el estado"
                )
        
        if new_status == "terminado":
            update_dict["completed_at"] = datetime.utcnow()
        elif new_status != "terminado" and current_status == "terminado":
            # If reverting from terminado, clear completed_at (admin only)
            update_dict["completed_at"] = None
    
    result = await db.work_orders.update_one(
        {"id": order_id, "workshop_id": current_user["workshop_id"]},
        {"$set": update_dict}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="No se pudo actualizar la orden")
    
    # Log status change
    if "status" in update_dict:
        await db.order_history.insert_one({
            "id": str(uuid.uuid4()),
            "work_order_id": order_id,
            "user_id": current_user["id"],
            "user_name": current_user["name"],
            "action": f"Estado cambiado a {update_dict['status']}",
            "timestamp": datetime.utcnow()
        })
    
    return {"message": "Orden actualizada"}

# ============ PAYMENT ROUTES ============

@api_router.post("/payments")
async def create_payment(payment_data: PaymentCreate, current_user: dict = Depends(get_current_user)):
    # Check if payment exists
    existing = await db.payments.find_one({"work_order_id": payment_data.work_order_id})
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un pago para esta orden")
    
    payment_obj = Payment(
        workshop_id=current_user["workshop_id"],
        **payment_data.dict()
    )
    await db.payments.insert_one(payment_obj.dict())
    return payment_obj.dict()

@api_router.put("/payments/{payment_id}")
async def update_payment(payment_id: str, payment_data: PaymentUpdate, current_user: dict = Depends(get_current_user)):
    update_dict = {k: v for k, v in payment_data.dict().items() if v is not None}
    update_dict["updated_at"] = datetime.utcnow()
    
    result = await db.payments.update_one(
        {"id": payment_id, "workshop_id": current_user["workshop_id"]},
        {"$set": update_dict}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    
    return {"message": "Pago actualizado"}

@api_router.get("/payments/{work_order_id}")
async def get_payment(work_order_id: str, current_user: dict = Depends(get_current_user)):
    payment = await db.payments.find_one({
        "work_order_id": work_order_id,
        "workshop_id": current_user["workshop_id"]
    })
    return serialize_doc(payment)

# ============ REPORTS ============

@api_router.get("/reports/daily")
async def get_daily_report(
    date: Optional[str] = None,
    tech_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    # Default to today
    if date:
        try:
            filter_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            filter_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        filter_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    next_day = filter_date + timedelta(days=1)
    
    query = {
        "workshop_id": current_user["workshop_id"],
        "created_at": {"$gte": filter_date, "$lt": next_day}
    }
    
    if tech_id:
        query["tech_id"] = tech_id
    elif current_user["role"] != "admin":
        query["tech_id"] = current_user["id"]
    
    orders = await db.work_orders.find(query).to_list(1000)
    
    total_orders = len(orders)
    total_billed = 0.0
    total_paid = 0.0
    total_pending = 0.0
    
    by_status = {"iniciado": 0, "pendiente": 0, "terminado": 0}
    by_tech = {}
    
    for order in orders:
        status = order.get("status", "iniciado")
        by_status[status] = by_status.get(status, 0) + 1
        
        tech_id_order = order.get("tech_id", "")
        if tech_id_order not in by_tech:
            tech = await db.users.find_one({"id": tech_id_order})
            by_tech[tech_id_order] = {
                "name": tech["name"] if tech else "Desconocido",
                "orders": 0,
                "billed": 0.0,
                "paid": 0.0
            }
        by_tech[tech_id_order]["orders"] += 1
        
        payment = await db.payments.find_one({"work_order_id": order["id"]})
        if payment:
            total_billed += payment.get("total", 0)
            by_tech[tech_id_order]["billed"] += payment.get("total", 0)
            
            if payment.get("payment_status") == "pagado":
                total_paid += payment.get("paid_amount", 0)
                by_tech[tech_id_order]["paid"] += payment.get("paid_amount", 0)
            else:
                total_pending += payment.get("total", 0) - payment.get("paid_amount", 0)
    
    return {
        "date": filter_date.strftime("%Y-%m-%d"),
        "total_orders": total_orders,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "total_pending": total_pending,
        "by_status": by_status,
        "by_tech": list(by_tech.values())
    }

# ============ WORKSHOP SETTINGS ============

@api_router.get("/workshop")
async def get_workshop(current_user: dict = Depends(get_current_user)):
    workshop = await db.workshops.find_one({"id": current_user["workshop_id"]})
    if not workshop:
        raise HTTPException(status_code=404, detail="Taller no encontrado")
    return serialize_doc(workshop)

@api_router.put("/workshop")
async def update_workshop(
    tax_rate: Optional[float] = None,
    name: Optional[str] = None,
    address: Optional[str] = None,
    phone: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede modificar configuración")
    
    update_dict = {}
    if tax_rate is not None:
        update_dict["tax_rate"] = tax_rate
    if name is not None:
        update_dict["name"] = name
    if address is not None:
        update_dict["address"] = address
    if phone is not None:
        update_dict["phone"] = phone
    
    if update_dict:
        await db.workshops.update_one(
            {"id": current_user["workshop_id"]},
            {"$set": update_dict}
        )
    
    return {"message": "Configuración actualizada"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

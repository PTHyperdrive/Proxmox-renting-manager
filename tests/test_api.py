"""
Tests for API Endpoints

Tests the FastAPI endpoints using TestClient.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

# Note: These tests require the database to be initialized
# They use test fixtures to set up test data


class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test that health endpoint returns healthy status"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data


class TestVMEndpoints:
    """Test VM-related endpoints"""
    
    def test_list_vms_empty(self, client):
        """Test listing VMs when database is empty"""
        response = client.get("/api/vms")
        
        assert response.status_code == 200
        data = response.json()
        assert "vms" in data
        assert "total" in data
    
    def test_get_vm_not_found(self, client):
        """Test getting a non-existent VM"""
        response = client.get("/api/vms/99999")
        
        assert response.status_code == 404


class TestSessionEndpoints:
    """Test session-related endpoints"""
    
    def test_list_sessions_empty(self, client):
        """Test listing sessions when database is empty"""
        response = client.get("/api/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total" in data
        assert data["page"] == 1
    
    def test_list_sessions_with_pagination(self, client):
        """Test session pagination parameters"""
        response = client.get("/api/sessions?page=1&per_page=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 10
    
    def test_get_running_sessions(self, client):
        """Test getting currently running sessions"""
        response = client.get("/api/sessions/running")
        
        assert response.status_code == 200
        data = response.json()
        assert "running_count" in data
        assert "sessions" in data
    
    def test_manual_start_session(self, client):
        """Test manually starting a session"""
        response = client.post("/api/sessions/manual/start?vm_id=100&node=pve1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Session started"
        assert data["session"]["vm_id"] == "100"
        assert data["session"]["is_running"] == True
    
    def test_manual_stop_session(self, client):
        """Test manually stopping a session"""
        # First start a session
        start_response = client.post("/api/sessions/manual/start?vm_id=101&node=pve1")
        session_id = start_response.json()["session"]["id"]
        
        # Then stop it
        response = client.post(f"/api/sessions/manual/stop/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Session stopped"
        assert data["session"]["is_running"] == False
        assert data["session"]["duration_seconds"] is not None
    
    def test_stop_nonexistent_session(self, client):
        """Test stopping a session that doesn't exist"""
        response = client.post("/api/sessions/manual/stop/99999")
        
        assert response.status_code == 404
    
    def test_sync_sessions(self, client):
        """Test syncing sessions from Proxmox"""
        # This will likely fail to connect but should return a valid response
        response = client.post("/api/sessions/sync")
        
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data


class TestRentalEndpoints:
    """Test rental-related endpoints"""
    
    def test_list_rentals_empty(self, client):
        """Test listing rentals when database is empty"""
        response = client.get("/api/rentals")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_rental(self, client):
        """Test creating a new rental"""
        rental_data = {
            "vm_id": "100",
            "customer_name": "Test Customer",
            "customer_email": "test@example.com",
            "rental_start": "2024-01-01T00:00:00",
            "billing_cycle": "monthly",
            "rate_per_hour": 0.50
        }
        
        response = client.post("/api/rentals", json=rental_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["vm_id"] == "100"
        assert data["customer_name"] == "Test Customer"
        assert data["is_active"] == True
    
    def test_get_rental(self, client):
        """Test getting a specific rental"""
        # First create a rental
        rental_data = {
            "vm_id": "102",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Then get it
        response = client.get(f"/api/rentals/{rental_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == rental_id
        assert data["vm_id"] == "102"
    
    def test_update_rental(self, client):
        """Test updating a rental"""
        # First create a rental
        rental_data = {
            "vm_id": "103",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Then update it
        update_data = {
            "customer_name": "Updated Customer",
            "rate_per_hour": 1.00
        }
        response = client.put(f"/api/rentals/{rental_id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["customer_name"] == "Updated Customer"
        assert data["rate_per_hour"] == 1.00
    
    def test_delete_rental(self, client):
        """Test deleting a rental"""
        # First create a rental
        rental_data = {
            "vm_id": "104",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Then delete it
        response = client.delete(f"/api/rentals/{rental_id}")
        
        assert response.status_code == 200
        
        # Verify it's deleted
        get_response = client.get(f"/api/rentals/{rental_id}")
        assert get_response.status_code == 404
    
    def test_set_rental_start_month(self, client):
        """Test setting rental start month"""
        # First create a rental
        rental_data = {
            "vm_id": "105",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Set start month
        response = client.post(f"/api/rentals/{rental_id}/set-start-month?year=2024&month=3")
        
        assert response.status_code == 200
        data = response.json()
        assert "2024-03-01" in data["rental"]["rental_start"]
    
    def test_get_usage_report(self, client):
        """Test getting usage report for a rental"""
        # First create a rental
        rental_data = {
            "vm_id": "106",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Get usage report
        response = client.get(f"/api/rentals/{rental_id}/report")
        
        assert response.status_code == 200
        data = response.json()
        assert data["rental_id"] == rental_id
        assert "total_seconds" in data
        assert "session_count" in data
    
    def test_get_monthly_report(self, client):
        """Test getting monthly usage report"""
        # First create a rental
        rental_data = {
            "vm_id": "107",
            "rental_start": "2024-01-01T00:00:00"
        }
        create_response = client.post("/api/rentals", json=rental_data)
        rental_id = create_response.json()["id"]
        
        # Get monthly report
        response = client.get(f"/api/rentals/{rental_id}/monthly/2024/1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2024
        assert data["month"] == 1
        assert "total_seconds" in data


class TestDashboard:
    """Test web dashboard endpoint"""
    
    def test_dashboard_loads(self, client):
        """Test that dashboard HTML loads"""
        response = client.get("/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Proxmox VM Tracker" in response.text


# Pytest fixtures
@pytest.fixture
def client():
    """Create a test client with fresh database"""
    import asyncio
    from app.main import app
    from app.models.database import init_db, engine, Base
    
    # Create tables
    async def setup_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    
    asyncio.get_event_loop().run_until_complete(setup_db())
    
    with TestClient(app) as test_client:
        yield test_client

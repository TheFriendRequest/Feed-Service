from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

# --------------------------
# Post Schemas
# --------------------------
class PostBase(BaseModel):
    title: str
    body: Optional[str] = None
    image_url: Optional[str] = None

class PostCreate(PostBase):
    interest_ids: Optional[List[int]] = []  # List of interest IDs to associate with the post

class PostUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    interest_ids: Optional[List[int]] = None

class PostResponse(PostBase):
    post_id: int
    created_by: int
    created_at: datetime
    interests: Optional[List[dict]] = []  # List of interest objects
    links: Optional[dict] = {}  # HATEOAS links

    class Config:
        orm_mode = True

class InterestResponse(BaseModel):
    interest_id: int
    interest_name: str


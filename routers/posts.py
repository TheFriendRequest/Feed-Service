from fastapi import APIRouter, HTTPException, Depends, status, Query, Header, Response, Request
from typing import Optional, Dict, Any, List, cast
from datetime import datetime
import os
import sys
import hashlib
import json
import mysql.connector  # type: ignore
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Authentication removed - trust x-firebase-uid header from API Gateway
from model import PostCreate, PostUpdate, PostResponse, InterestResponse

router = APIRouter(prefix="/posts", tags=["Posts"])

# ----------------------
# DB Connection
# ----------------------
def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", "admin"),
        database=os.getenv("DB_NAME", "feed_db")
    )


# ----------------------
# Helper: Get firebase_uid from header (set by API Gateway)
# ----------------------
def get_firebase_uid_from_header(request: Request) -> str:
    """Get firebase_uid from x-firebase-uid header (injected by API Gateway)"""
    firebase_uid = request.headers.get("x-firebase-uid") or request.headers.get("X-Firebase-Uid")
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Authentication required - x-firebase-uid header missing")
    return firebase_uid

# ----------------------
# Helper: Generate eTag
# ----------------------
def generate_etag(data: dict) -> str:
    """Generate eTag from data"""
    data_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(data_str.encode()).hexdigest()


# ----------------------
# Helper: Add HATEOAS links
# ----------------------
def add_links(post_id: int, base_url: str = "") -> dict:
    """Add HATEOAS links to post"""
    return {
        "self": {"href": f"{base_url}/posts/{post_id}"},
        "collection": {"href": f"{base_url}/posts"},
        "interests": {"href": f"{base_url}/posts/{post_id}/interests"},
        "author": {"href": f"{base_url}/users/{post_id}"}  # Relative path example
    }


# ----------------------
# Helper: Get interests for a post
# ----------------------
def get_post_interests(post_id: int) -> List[Dict[str, Any]]:
    """Get interests associated with a post"""
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    cur.execute("""
        SELECT i.interest_id, i.interest_name
        FROM Interests i
        INNER JOIN PostInterests pi ON i.interest_id = pi.interest_id
        WHERE pi.post_id = %s
    """, (post_id,))
    interests = cast(List[Dict[str, Any]], cur.fetchall())
    cur.close()
    cnx.close()
    return interests


# ----------------------
# CRUD Endpoints
# ----------------------
@router.get("/", response_model=Dict[str, Any])
def get_posts(
    response: Response,
    request: Request,
    skip: int = Query(0, ge=0, description="Number of posts to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of posts to return"),
    interest_id: Optional[int] = Query(None, description="Filter by interest ID"),
    created_by: Optional[int] = Query(None, description="Filter by creator user ID"),
    search: Optional[str] = Query(None, description="Search in title and body")
):
    """
    Get all posts with pagination and query parameters.
    Supports filtering by interest_id, created_by, and search.
    Returns HATEOAS links and pagination metadata.
    Trusts x-firebase-uid header from API Gateway.
    """
    firebase_uid = get_firebase_uid_from_header(request)
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    
    # Build query with filters
    where_clauses = []
    params = []
    
    if interest_id:
        where_clauses.append("p.post_id IN (SELECT post_id FROM PostInterests WHERE interest_id = %s)")
        params.append(interest_id)
    
    if created_by:
        where_clauses.append("p.created_by = %s")
        params.append(created_by)
    
    if search:
        where_clauses.append("(p.title LIKE %s OR p.body LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Get total count
    count_query = f"SELECT COUNT(*) as total FROM Posts p WHERE {where_sql}"
    cur.execute(count_query, tuple(params))
    count_result = cast(Optional[Dict[str, Any]], cur.fetchone())
    total = int(count_result['total']) if count_result and 'total' in count_result else 0
    
    # Get paginated posts
    query = f"""
        SELECT p.post_id, p.title, p.body, p.image_url, p.created_by, p.created_at
        FROM Posts p
        WHERE {where_sql}
        ORDER BY p.created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, skip])
    cur.execute(query, tuple(params))
    posts = cast(List[Dict[str, Any]], cur.fetchall())
    
    cur.close()
    cnx.close()
    
    # Add interests and links to each post
    for post in posts:
        post_id = int(post['post_id']) if post.get('post_id') is not None else None
        if post_id:
            post['interests'] = get_post_interests(post_id)
            post['links'] = add_links(post_id)
        # Convert datetime to string
        if post.get('created_at') and isinstance(post['created_at'], datetime):
            post['created_at'] = post['created_at'].isoformat()
    
    # Generate eTag for the collection
    etag = generate_etag({"posts": posts, "total": total, "skip": skip, "limit": limit})
    response.headers["ETag"] = f'"{etag}"'
    print(f"[Feed Service] Generated ETag for posts collection: {etag}")
    print(f"[Feed Service] ETag header set: {response.headers.get('ETag')}")
    
    # Return with pagination metadata and HATEOAS links
    return {
        "items": posts,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total,
        "links": {
            "self": {"href": f"/posts?skip={skip}&limit={limit}"},
            "first": {"href": f"/posts?skip=0&limit={limit}"},
            "last": {"href": f"/posts?skip={max(0, (total - 1) // limit * limit)}&limit={limit}"},
            "next": {"href": f"/posts?skip={skip + limit}&limit={limit}"} if (skip + limit) < total else None,
            "prev": {"href": f"/posts?skip={max(0, skip - limit)}&limit={limit}"} if skip > 0 else None
        }
    }


@router.get("/{post_id}", response_model=PostResponse)
def get_post(
    post_id: int,
    response: Response,
    request: Request,
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    """
    Get a specific post by ID with eTag support.
    Returns 304 Not Modified if eTag matches.
    Trusts x-firebase-uid header from API Gateway.
    """
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    cur.execute("""
        SELECT post_id, title, body, image_url, created_by, created_at
        FROM Posts
        WHERE post_id = %s
    """, (post_id,))
    post = cast(Optional[Dict[str, Any]], cur.fetchone())
    cur.close()
    cnx.close()
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Add interests
    post['interests'] = get_post_interests(post_id)
    
    # Convert datetime to string
    if post.get('created_at') and isinstance(post['created_at'], datetime):
        post['created_at'] = post['created_at'].isoformat()
    
    # Generate eTag
    etag = generate_etag(post)
    response.headers["ETag"] = f'"{etag}"'
    
    # Check if client has matching eTag
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)
    
    # Add HATEOAS links
    post['links'] = add_links(post_id)
    
    return post


@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    post: PostCreate,
    response: Response,
    request: Request
):
    """
    Create a new post.
    The created_by field must be provided in the request body (user_id from Composite Service).
    Trusts x-firebase-uid header from API Gateway.
    Returns 201 Created with Location header.
    """
    firebase_uid = get_firebase_uid_from_header(request)
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    
    # Create post
    sql = """
        INSERT INTO Posts (title, body, image_url, created_by)
        VALUES (%s, %s, %s, %s)
    """
    values = (post.title, post.body, post.image_url, post.created_by)
    cur.execute(sql, values)
    cnx.commit()
    post_id = cur.lastrowid
    
    if not post_id:
        cur.close()
        cnx.close()
        raise HTTPException(status_code=500, detail="Failed to create post")
    
    post_id_int = int(post_id)
    
    # Associate interests if provided
    if post.interest_ids:
        for interest_id in post.interest_ids:
            # Verify interest exists
            cur.execute("SELECT interest_id FROM Interests WHERE interest_id = %s", (interest_id,))
            if not cur.fetchone():
                cur.close()
                cnx.close()
                raise HTTPException(status_code=400, detail=f"Interest {interest_id} not found")
            
            cur.execute(
                "INSERT INTO PostInterests (post_id, interest_id) VALUES (%s, %s)",
                (post_id_int, interest_id)
            )
        cnx.commit()
    
    # Fetch the created post
    cur.execute("""
        SELECT post_id, title, body, image_url, created_by, created_at
        FROM Posts
        WHERE post_id = %s
    """, (post_id_int,))
    created_post = cast(Optional[Dict[str, Any]], cur.fetchone())
    cur.close()
    cnx.close()
    
    if not created_post:
        raise HTTPException(status_code=500, detail="Failed to retrieve created post")
    
    # Add interests and links
    created_post['interests'] = get_post_interests(post_id_int)
    created_post['links'] = add_links(post_id_int)
    
    # Convert datetime to string
    if created_post.get('created_at') and isinstance(created_post['created_at'], datetime):
        created_post['created_at'] = created_post['created_at'].isoformat()
    
    # Set Location header
    response.headers["Location"] = f"/posts/{post_id_int}"
    
    return created_post


@router.put("/{post_id}", response_model=PostResponse)
def update_post(
    post_id: int,
    post: PostUpdate,
    response: Response,
    request: Request,
    created_by: int = Query(..., description="User ID of the creator (for authorization check)"),
    if_match: Optional[str] = Header(None, alias="If-Match")
):
    """
    Update a post.
    Supports eTag validation with If-Match header.
    The created_by query parameter is used to verify the user is the creator.
    Trusts x-firebase-uid header from API Gateway.
    """
    firebase_uid = get_firebase_uid_from_header(request)
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    
    # Check if post exists and user is the creator
    cur.execute("""
        SELECT post_id, title, body, image_url, created_by, created_at
        FROM Posts WHERE post_id = %s
    """, (post_id,))
    existing_post = cast(Optional[Dict[str, Any]], cur.fetchone())
    
    if not existing_post:
        cur.close()
        cnx.close()
        raise HTTPException(status_code=404, detail="Post not found")
    
    if existing_post.get('created_by') != created_by:
        cur.close()
        cnx.close()
        raise HTTPException(
            status_code=403,
            detail="You can only update posts you created"
        )
    
    # Check eTag if provided
    if if_match:
        existing_post['interests'] = get_post_interests(post_id)
        existing_etag = generate_etag(existing_post)
        if if_match.strip('"') != existing_etag:
            cur.close()
            cnx.close()
            raise HTTPException(status_code=412, detail="Precondition Failed: eTag mismatch")
    
    # Build dynamic SQL for update
    fields = []
    values = []
    
    update_dict = post.dict(exclude_unset=True)
    
    # Handle interest_ids separately
    interest_ids = update_dict.pop('interest_ids', None)
    
    for key, value in update_dict.items():
        if value is not None:
            fields.append(f"{key} = %s")
            values.append(value)
    
    if fields:
        sql = f"UPDATE Posts SET {', '.join(fields)} WHERE post_id = %s"
        values.append(post_id)
        cur.execute(sql, tuple(values))
        cnx.commit()
    
    # Update interests if provided
    if interest_ids is not None:
        # Delete existing associations
        cur.execute("DELETE FROM PostInterests WHERE post_id = %s", (post_id,))
        
        # Add new associations
        for interest_id in interest_ids:
            # Verify interest exists
            cur.execute("SELECT interest_id FROM Interests WHERE interest_id = %s", (interest_id,))
            if not cur.fetchone():
                cur.close()
                cnx.close()
                raise HTTPException(status_code=400, detail=f"Interest {interest_id} not found")
            
            cur.execute(
                "INSERT INTO PostInterests (post_id, interest_id) VALUES (%s, %s)",
                (post_id, interest_id)
            )
        cnx.commit()
    
    # Fetch the updated post
    cur.execute("""
        SELECT post_id, title, body, image_url, created_by, created_at
        FROM Posts
        WHERE post_id = %s
    """, (post_id,))
    updated_post = cast(Optional[Dict[str, Any]], cur.fetchone())
    cur.close()
    cnx.close()
    
    if not updated_post:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated post")
    
    # Add interests and links
    updated_post['interests'] = get_post_interests(post_id)
    updated_post['links'] = add_links(post_id)
    
    # Convert datetime to string
    if updated_post.get('created_at') and isinstance(updated_post['created_at'], datetime):
        updated_post['created_at'] = updated_post['created_at'].isoformat()
    
    # Generate new eTag
    etag = generate_etag(updated_post)
    response.headers["ETag"] = f'"{etag}"'
    
    return updated_post


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    request: Request,
    created_by: int = Query(..., description="User ID of the creator (for authorization check)")
):
    """
    Delete a post.
    The created_by query parameter is used to verify the user is the creator.
    Trusts x-firebase-uid header from API Gateway.
    """
    firebase_uid = get_firebase_uid_from_header(request)
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    
    # Check if post exists and user is the creator
    cur.execute("""
        SELECT created_by FROM Posts WHERE post_id = %s
    """, (post_id,))
    post = cast(Optional[Dict[str, Any]], cur.fetchone())
    
    if not post:
        cur.close()
        cnx.close()
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.get('created_by') != created_by:
        cur.close()
        cnx.close()
        raise HTTPException(
            status_code=403,
            detail="You can only delete posts you created"
        )
    
    cur.execute("DELETE FROM Posts WHERE post_id = %s", (post_id,))
    cnx.commit()
    cur.close()
    cnx.close()
    
    return {"status": "deleted", "post_id": post_id}


# ----------------------
# Interests endpoints
# ----------------------
@router.get("/interests/")
def get_interests(request: Request):
    """Get all available interests. Trusts x-firebase-uid header from API Gateway."""
    firebase_uid = get_firebase_uid_from_header(request)
    cnx = get_connection()
    cur = cnx.cursor(dictionary=True)
    cur.execute("SELECT interest_id, interest_name FROM Interests ORDER BY interest_name")
    interests = cast(List[Dict[str, Any]], cur.fetchall())
    cur.close()
    cnx.close()
    return interests


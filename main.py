import base64
import json
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from hashlib import sha256

import dotenv
import redis
from fastapi import Depends, FastAPI, Response, responses
from pydantic import BaseModel

app = FastAPI()

dotenv.load_dotenv()

# SQLITE
@contextmanager
def get_sqldb_connection():
    conn = sqlite3.connect(os.environ["SQLITE_DB_PATH"])
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
def get_sqldb():
    with get_sqldb_connection() as conn:
        yield conn

# REDIS
@contextmanager
def get_redis_connection():
    rconn = redis.Redis(os.environ["REDIS_URL"], int(os.environ["REDIS_PORT"]), 0, os.environ["REDIS_PASSWORD"])
    try:
        yield rconn
    finally:
        rconn.close()
def get_redisdb():
    with get_redis_connection() as conn:
        yield conn

class User(BaseModel):
    name: str
    password: str

@app.post("/user/register")
def user_register(user: User, sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if sqldb.execute("SELECT * FROM users WHERE name=?", (user.name,)).fetchone() is not None:
        return Response("error: user already exist", status_code=409)
    hashpw = sha256(user.password.encode()).hexdigest()
    
    token = base64.b64encode(random.randbytes(32)).decode()
    while True:
        if sqldb.execute("SELECT token FROM users WHERE token=?", (user.name,)).fetchone() is None:
            break
        token = base64.b64encode(random.randbytes(32)).decode()
    
    sqldb.execute("INSERT INTO users (name, passwordhash, token) values (?, ?, ?)", (user.name, hashpw, token))
    sqldb.commit()
    return responses.JSONResponse({"token": token})

@app.post("/user/auth")
def user_auth(user: User, sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if (user_req:=sqldb.execute("SELECT name, passwordhash FROM users WHERE name=?", (user.name,)).fetchone()) is None:
        return Response("error: user doesnt exist", status_code=404)
    hashpw = sha256(user.password.encode()).hexdigest()
    if user_req[1] != hashpw:
        return Response("error: password doenst match", status_code=401)
    
    token = base64.b64encode(random.randbytes(32)).decode()
    while True:
        if sqldb.execute("SELECT token FROM users WHERE token=?", (user.name,)).fetchone() is None:
            break
        token = base64.b64encode(random.randbytes(32)).decode()
    
    sqldb.execute("UPDATE users SET token=? WHERE name=?", (token, user.name))
    sqldb.commit()
    return responses.JSONResponse({"token": token})

class Company(BaseModel):
    name: str
    password: str

@app.post("/company/register")
def company_register(company: Company, sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if sqldb.execute("SELECT * FROM companies WHERE name=?", (company.name,)).fetchone() is not None:
        return Response("error: company already exist", status_code=409)
    hashpw = sha256(company.password.encode()).hexdigest()

    token = base64.b64encode(random.randbytes(32)).decode()
    while True:
        if sqldb.execute("SELECT token FROM companies WHERE token=?", (company.name,)).fetchone() is None:
            break
        token = base64.b64encode(random.randbytes(32)).decode()
    
    sqldb.execute("INSERT INTO companies (name, passwordhash, token) values (?, ?, ?)", (company.name, hashpw, token))
    sqldb.commit()
    return responses.JSONResponse({"token": token})

@app.post("/company/auth")
def company_auth(company: Company, sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if (company_req:=sqldb.execute("SELECT name, passwordhash FROM companies WHERE name=?", (company.name,)).fetchone()) is None:
        return Response("error: company doesnt exist", status_code=404)
    hashpw = sha256(company.password.encode()).hexdigest()
    if company_req[1] != hashpw:
        return Response("error: password doenst match", status_code=401)
    
    token = base64.b64encode(random.randbytes(32)).decode()
    while True:
        if sqldb.execute("SELECT token FROM companies WHERE token=?", (company.name,)).fetchone() is None:
            break
        token = base64.b64encode(random.randbytes(32)).decode()
    
    sqldb.execute("UPDATE users SET token=? WHERE name=?", (token, company.name))
    sqldb.commit()
    return responses.JSONResponse({"token": token})

class Token(BaseModel):
    token: str

@app.post("/subscribe/{cname}")
def subscribe(cname: str, utoken: Token, sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if (company_id:=sqldb.execute("SELECT id FROM companies WHERE name=?", (cname,)).fetchone()) is None:
        return Response("error: company doesnt exist", status_code=404)
    if (user_id:=sqldb.execute("SELECT id FROM users WHERE token=?", (utoken.token,)).fetchone()) is None:
        return Response("error: token doesnt exist", status_code=401)

    subscribe = base64.b64encode(random.randbytes(32)).decode()
    while True:
        if sqldb.execute("SELECT subscribe FROM pairs WHERE subscribe=?", (subscribe,)).fetchone() is None:
            break
        subscribe = base64.b64encode(random.randbytes(32)).decode()

    if (subscribe_id:=sqldb.execute("SELECT id FROM pairs WHERE user_id=? AND company_id=?", (user_id[0], company_id[0])).fetchone()) is None:
        sqldb.execute("INSERT INTO pairs (subscribe, user_id, company_id) values (?, ?, ?)", (subscribe, user_id[0], company_id[0]))
    else:
        sqldb.execute("UPDATE pairs SET subscribe=? WHERE id=?", (subscribe, subscribe_id[0]))
    sqldb.commit()
    
    return responses.JSONResponse({"subscribe_id": subscribe})

class Post(BaseModel):
    ctoken: str
    stoken: str
    data: str

@app.post("/publish")
def publish(post: Post, redisdb: redis.Redis = Depends(get_redisdb), sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if (company:=sqldb.execute("SELECT id, name FROM companies WHERE token=?", (post.ctoken,)).fetchone()) is None:
        return Response("error: token doesnt exist", status_code=401)
    if (pair:=sqldb.execute("SELECT user_id FROM pairs WHERE subscribe=? AND company_id=?", (post.stoken, company[0])).fetchone()) is None:
        return Response("error: pair doesnt exist", status_code=404)

    pipe = redisdb.pipeline()
    d = {"company": company[1], "data": post.data, "dt": time.time()}
    d = json.dumps(d)
    pipe.rpush(pair[0], d)
    pipe.expire(pair[0], 86400)
    pipe.execute()

    return Response(status_code=204)

@app.get("/notifies")
def notifies(token: Token, redisdb: redis.Redis = Depends(get_redisdb), sqldb: sqlite3.Connection = Depends(get_sqldb)):
    if (user_id:=sqldb.execute("SELECT id FROM users WHERE token=?", (token.token, )).fetchone()) is None:
        return Response("error: token doesnt exist", status_code=401)

    pipe = redisdb.pipeline()
    data = pipe.lrange(user_id[0], 0, -1)
    
    pipe.delete(user_id[0])

    results = pipe.execute()
    if results[0]:
        data = [i.decode() for i in results[0]]
    else:
        data = {}

    return responses.JSONResponse(data)

with get_sqldb_connection() as con:
    con.execute('''
CREATE TABLE IF NOT EXISTS "users" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL UNIQUE,
	"passwordhash"	TEXT NOT NULL,
	"token"	TEXT NOT NULL UNIQUE,
	PRIMARY KEY("id" AUTOINCREMENT)
)
''')
    con.execute('''
CREATE TABLE IF NOT EXISTS "companies" (
	"id"	INTEGER NOT NULL UNIQUE,
	"name"	TEXT NOT NULL UNIQUE,
	"passwordhash"	TEXT NOT NULL,
	"token"	TEXT NOT NULL UNIQUE,
	PRIMARY KEY("id" AUTOINCREMENT)
)
''')
    con.execute('''
CREATE TABLE IF NOT EXISTS "pairs" (
	"id"	INTEGER NOT NULL UNIQUE,
	"subscribe"	TEXT NOT NULL UNIQUE,
	"user_id"	INTEGER NOT NULL,
	"company_id"	INTEGER NOT NULL,
	PRIMARY KEY("id" AUTOINCREMENT)
)
''')
    con.commit()

# uvicorn main:app --reload --host 0.0.0.0 --port 39080

from sqlalchemy import Column, Float, String
class User(Base):
    email = Column(String)
    phone_number = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    resident_number = Column(String)

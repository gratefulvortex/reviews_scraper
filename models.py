from firebase_admin import auth
from config.firebase_config import initialize_firebase

db = initialize_firebase()

class User:
    def __init__(self, email, uid=None):
        self.email = email
        self.uid = uid
        self.is_authenticated = False
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return self.uid

    @staticmethod
    def create_user(email, password):
        try:
            user = auth.create_user(
                email=email,
                password=password
            )
            # Store additional user data in Firestore
            db.collection('users').document(user.uid).set({
                'email': email,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            return User(email=email, uid=user.uid)
        except Exception as e:
            raise Exception(f"Error creating user: {str(e)}")

    @staticmethod
    def get_user_by_email(email):
        try:
            user = auth.get_user_by_email(email)
            return User(email=user.email, uid=user.uid)
        except:
            return None

    @staticmethod
    def get_user_by_id(uid):
        try:
            user = auth.get_user(uid)
            return User(email=user.email, uid=user.uid)
        except:
            return None
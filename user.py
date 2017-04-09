import random
import hashlib

from string import letters
from google.appengine.ext import db


# Helper functions create 5 letters salt
def make_salt(length=5):
    return ''.join(random.choice(letters) for x in xrange(length))

# implement hashing
def make_pw_hash(name, pw, salt=None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

# compare password
def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)


def users_key(group='default'):
    return db.Key.from_path('users', group)


# User Model
class User(db.Model):
    """
        This is a User Class, which holds user information.
        And helps to store/retrieve User data to/from database.

        Attributes:
            name (int): This is name of the user.
            pw_hash (str): This is hashed password of the post.
            email (text): This is email of the user.
    """
    name = db.StringProperty(required=True)
    pw_hash = db.StringProperty(required=True)
    email = db.StringProperty()

    @classmethod
    def by_id(self, uid):
        """
            This method fetchs User object from database, whose id is {uid}.
        """
        return User.get_by_id(uid, parent=users_key())

    @classmethod
    def by_name(self, name):
        """
            This method fetchs List of User objects from database,
            whose name is {name}.
        """
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(self, name, pw, email=None):
        """
            This method creates a new User in database.
        """
        pw_hash = make_pw_hash(name, pw)
        return User(parent=users_key(),
                    name=name,
                    pw_hash=pw_hash,
                    email=email)

    @classmethod
    def login(self, name, pw):
        """
            This method creates a new User in database.
        """
        u = self.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u

import os
import jinja2
import webapp2
import re
import hmac
import hashlib
import random

from string import letters

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
    autoescape = True)


# Global function for rendering a string which does not inherit from the class Handler

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


# functions for hashing and validating password hashing

secret = 'aaarfh-this_is-sooooo_secreteeeeeer-than_anything-ion'

def make_secure_val(val):
    return "%s|%s" % (val, hmac.new(secret, val).hexdigest())

def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class Handler(webapp2.RequestHandler):
    """class that handles rendering and writing and can be used
       in other classes that inherit from it"""
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


class Entrance(Handler):
    """class that renders a start page, just for the sake of it"""
    def get(self):
        self.render("entrance.html")


# Functions for hashing and salting

def make_salt():
    return ''.join(random.choice(letters) for x in range(5))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    hashstring = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, hashstring)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)


class User(db.Model):
    """class that creates the basic database specifics for a user"""
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Posts(db.Model):
    """class that creates the basic database specifics for a blog post"""
    subject = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    author = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)

    def render(self):
        self.render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)


class PostHandler(Handler):
    """class that shows a newly created blog post"""
    def get(self, post_id):
        key = db.Key.from_path('Posts', int(post_id), parent = blog_key())
        p = db.get(key)

        if not p:
            self.error(404)
            return

        self.render("permalink.html", p = p)


class NewPost(Handler):
    """class that renders a form page for creating a new blog post"""
    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            error = "You need to be logged in to write a new post!"
            self.render('login.html', error=error)

    def post(self):
        if not self.user:
            self.redirect("/blog")

        subject = self.request.get("subject")
        content = self.request.get("content")
        author = self.user.name

        if subject and content:
            p = Posts(parent = blog_key(), author=author, subject=subject, content=content)
            p.put()
            self.redirect("/blog/%s" % str(p.key().id()))
        else:
            error = "You have to fill in both subject and content fields!"
            self.render("newpost.html", subject=subject, content=content, error=error)


class EditPost(Handler):
    """class that opens an existing post for editing"""
    def get(self, post_id):
        key = db.Key.from_path('Posts', int(post_id), parent = blog_key())
        p = db.get(key)

        if self.user.name == p.author:
            self.render("edit.html", p=p, subject=p.subject, content=p.content)
            p.delete()
        else:
            error = "You need to be logged in to edit your post!"
            self.render('login.html', error=error)

    def post(self, post_id):

        subject = self.request.get("subject")
        content = self.request.get("content")
        author = self.user.name

        if subject and content:
            p = Posts(parent = blog_key(), author=author, subject=subject, content=content)
            p.put()
            self.redirect("/blog/%s" % str(p.key().id()))
        else:
            error = "You have to fill in both subject and content fields!"
            self.render("edit.html", p=p, subject=subject, content=content, error=error)



class DeletePost(Handler):
    """class for deleting a blog post"""
    def get(self, post_id):
        key = db.Key.from_path('Posts', int(post_id), parent = blog_key())
        p = db.get(key)

        if self.user.name == p.author:
            p.delete()
            self.render("blog.html", p=p)
        else:
            error = "You can only delete your own posts!"
            self.render("login.html", error=error)


class Comment(db.Model):
    """class that creates the basic database specifics for a comment"""
    comment = db.TextProperty(required=True)
    commentauthor = db.StringProperty(required=True)
    commentid = db.IntegerProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)


class CreateComment(Handler):
    """class that handles a new comment"""
    def get(self, post_id):
        key = db.Key.from_path('Posts', int(post_id), parent = blog_key())
        p = db.get(key)

        if self.user:
            if self.user.name != p.author:
                self.render("newcomment.html", p=p, subject=p.subject, content=p.content)
            else:
                error = "You can not comment your own posts!"
                self.redirect('/blog', message=error)

    def post(self, post_id):
        key = db.Key.from_path('Posts', int(post_id), parent = blog_key())
        p = db.get(key)

        comment = self.request.get("comment")
        commentauthor = self.user.name
        commentid = str(p.key().id())

        if comment and commentid:
            c = Comment(parent = blog_key(), comment=comment, commentauthor=commentauthor, commentid = commentid)
            c.put()
            self.redirect("/blog")
        else:
            error = "You have to enter text in the comment field!"
            self.render("newcomment.html", p=p, subject=p.subject, content=p.content, error=error)




# functions that check username, password and email for correct syntax in the signup form

username_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and username_RE.match(username)

password_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and password_RE.match(password)

email_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or email_RE.match(email)


class SignUpHandler(Handler):
    """class that renders the signup form and uses
       the functions above to check signup syntax"""
    def get(self):
        self.render('signup.html')

    def post(self):
        error_msg = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username, email = self.email)

        if not valid_username(self.username):
            params['username_error'] = "Username is invalid."
            error_msg = True

        if not valid_password(self.password):
            params['password_error'] = "Password is invalid."
            error_msg = True
        elif self.password != self.verify:
            params['verify_error'] = "Passwords didn't match."
            error_msg = True

        if not valid_email(self.email):
            params['email_error'] = "Email is invalid."
            error_msg = True

        if error_msg:
            self.render('signup.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Register(SignUpHandler):
    """class for registering a user, if the user is new and unique"""
    def done(self):
        u = User.by_name(self.username)
        if u:
            message = 'A user with that name already exists'
            self.render('signup.html', username_error = message)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/blog/welcome')


class Login(Handler):
    """login class"""
    def get(self):
        self.render('login.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog/welcome')
        else:
            message = 'Invalid login'
            self.render('login.html', error = message)


class Logout(Handler):
    """logout class"""
    def get(self):
        self.logout()
        self.redirect('/blog/signup')


class WelcomeHandler(Handler):
    """class that renders a welcome page when a new user has signed up"""
    def get(self):
        if self.user:
            self.render('welcome.html', username = self.user.name)
        else:
            self.redirect('/blog/signup')


class MainPage(Handler):
    """class that renders the main blog page"""
    def render_blog(self):
        posts = db.GqlQuery("SELECT * FROM Posts ORDER BY created DESC LIMIT 10")
        comments = db.GqlQuery("SELECT * FROM Comment ORDER BY created DESC LIMIT 10")
        self.render("blog.html", posts=posts, comments = comments)

    def get(self):
        self.render_blog()



app = webapp2.WSGIApplication([('/', Entrance),
                               ('/blog', MainPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/edit/([0-9]+)', EditPost),
                               ('/blog/([0-9]+)', PostHandler),
                               ('/blog/signup', Register),
                               ('/blog/welcome', WelcomeHandler),
                               ('/blog/login', Login),
                               ('/blog/logout', Logout),
                               ('/blog/deleted/([0-9]+)', DeletePost),
                               ('/blog/newcomment/([0-9]+)', CreateComment)
                             ],
                             debug=True)


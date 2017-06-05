import re
import hmac
import webapp2
import logging

from google.appengine.ext import db

from user import User
from post import Post
from comment import Comment
from like import Like
import TemplateFile
import hash_secret

# import secret for hashing fom hash_secret.py
secret = hash_secret.secret()


def make_secure_val(val):
    """
        Creates secure value using secret.
    """
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    """
        Verifies secure value compare secret.
    """
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class BlogHandler(webapp2.RequestHandler):
    """
        This is a BlogHandler Class, inherits webapp2.RequestHandler,
        and provides helper methods.
    """
    def write(self, *a, **kw):
        """
            This methods write output to client browser.
        """
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        """
            This methods renders html using template.
        """
        params['user'] = self.user
        return TemplateFile.jinja_render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        """
            Sets secure cookie to browser.
        """
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        """
            Reads secure cookie to browser.
        """
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        """
            Verifies user existance.
        """
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        """
            Removes login information from cookies.
        """
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        """
            This methods gets executed for each page and
            verfies user login status, using oookie information.
        """
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


class BlogFront(BlogHandler):
    def get(self):
        """
            This renders home page with all posts, sorted by date.
        """
        deleted_post_id = self.request.get('deleted_post_id')
        posts = greetings = Post.all().order('-created')
        self.render('front.html', posts=posts, deleted_post_id=deleted_post_id)


class PostPage(BlogHandler):
    def get(self, post_id):
        """
            This renders home post page with content, comments and likes.
        """
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        comments = db.GqlQuery("select * from Comment where post_id = " +
                               post_id + " order by created desc")

        likes = db.GqlQuery("select * from Like where post_id="+post_id)

        if not post:
            self.error(404)
            return

        error = self.request.get('error')

        self.render("permalink.html", post=post, noOfLikes=likes.count(),
                    comments=comments, error=error)

    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        """
            On posting comment, new comment tuple is created and stored,
            with relationship data of user and post.
        """
        c = ""
        if(self.user):
            # On clicking like, post-like value increases.
            if(self.request.get('like') and
               self.request.get('like') == "update"):
                likes = db.GqlQuery("select * from Like where post_id = " +
                                    post_id + " and user_id = " +
                                    str(self.user.key().id()))

                if self.user.key().id() == post.user_id:
                    self.redirect("/blog/" + post_id +
                                  "?error=You cannot like your " +
                                  "post.!!")
                    return
                elif likes.count() == 0:
                    l = Like(parent=blog_key(), user_id=self.user.key().id(),
                             post_id=int(post_id))
                    l.put()

            # On commenting, it creates new comment tuple
            if(self.request.get('comment')):
                c = Comment(parent=blog_key(), user_id=self.user.key().id(),
                            post_id=int(post_id),
                            comment=self.request.get('comment'))
                c.put()
        else:
            self.redirect("/login?error=You need to login before " +
                          "performing edit, like or commenting.!!")
            return

        comments = db.GqlQuery("select * from Comment where post_id = " +
                               post_id + "order by created desc")

        likes = db.GqlQuery("select * from Like where post_id="+post_id)

        self.render("permalink.html", post=post,
                    comments=comments, noOfLikes=likes.count(),
                    new=c)


class NewPost(BlogHandler):
    def get(self):
        if self.user:
            return self.render("newpost.html")
        else:
            return self.redirect("/login")

    def post(self):
        """
            Creates new post and redirect to new post page.
        """
        if not self.user:
            return self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent=blog_key(), user_id=self.user.key().id(),
                     subject=subject, content=content)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject,
                        content=content, error=error)


class DeletePost(BlogHandler):
    def get(self, post_id):
        if self.user:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            # check if the post exist in the database
            if not post:
                # if post does not exist, redirect to login page
                return self.redirect('/login')

            if post.user_id == self.user.key().id():
                post.delete()

                # delete all the comments associated with that post
                comments = Comment.all()
                comments.filter("post_id", int(post_id))
                for comment in comments:
                    comment.delete()

                self.redirect("/?deleted_post_id="+post_id)
            else:
                self.redirect("/blog/" + post_id + "?error=You don't have " +
                              "access to delete this record.")
        else:
            self.redirect("/login?error=You need to be logged, in order" +
                          " to delete your post!!")


class EditPost(BlogHandler):
    def get(self, post_id):
        if self.user:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            if not post:
                # if post does not exist, redirect to login page
                return self.redirect('/login')
            if post.user_id == self.user.key().id():
                self.render("editpost.html", subject=post.subject,
                            content=post.content)
            else:
                self.redirect("/blog/" + post_id + "?error=You don't have " +
                              "access to edit this record.")
        else:
            self.redirect("/login?error=You need to be logged, " +
                          "in order to edit your post!!")

    def post(self, post_id):
        """
            Updates post.
        """
        if not self.user:
            return self.redirect('/login')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if self.user:
            if subject and content:
                    key = db.Key.from_path('Post',
                                           int(post_id),
                                           parent=blog_key())
                    post = db.get(key)
                    # make sure the post exist
                    if not post:
                        # if post does not exist, redirect to login page
                        return self.redirect('/login')
                    # make sure the user owns the post
                    if self.user.key().id() != post.user_id:
                        # handle case
                        return self.redirect('/login')
                    post.subject = subject
                    post.content = content
                    post.put()
                    return self.redirect('/blog/%s' % post_id)
            else:
                error = "subject and content, please!"
                return self.render("editpost.html",
                                   subject=subject,
                                   content=content,
                                   error=error)


class DeleteComment(BlogHandler):

    def get(self, post_id, comment_id):
        if self.user:
            key = db.Key.from_path('Comment', int(comment_id),
                                   parent=blog_key())
            c = db.get(key)
            if not c:
                # if post does not exist, redirect to login page
                return self.redirect('/login')
            if c.user_id == self.user.key().id():
                c.delete()
                return self.redirect("/blog/"+post_id+"?deleted_comment_id=" +
                                     comment_id)
            else:
                return self.redirect("/blog/" + post_id +
                                     "?error=You don't have " +
                                     "access to delete this comment.")
        else:
            return self.redirect("/login?error=You need to be logged," +
                                 "in order to delete your comment!!")


class EditComment(BlogHandler):
    def get(self, post_id, comment_id):
        if self.user:
            key = db.Key.from_path('Comment',
                                   int(comment_id),
                                   parent=blog_key())
            c = db.get(key)
            if not c:
                return self.redirect('/login')
            if c.user_id == self.user.key().id():
                return self.render("editcomment.html", comment=c.comment)
            else:
                return self.redirect("/blog/" + post_id +
                                     "?error=You don't have access" +
                                     "to edit this comment.")
        else:
            return self.redirect("/login?error=You need to be logged," +
                                 "in order to edit your post!!")

    def post(self, post_id, comment_id):
        """
            Updates post.
        """
        if not self.user:
            return self.redirect('/blog')

        comment = self.request.get('comment')

        if not comment:
            # if post does not exist, redirect to login page
            return self.redirect('/login')
        # make sure the user owns the post
        if self.user:
            if comment:
                key = db.Key.from_path('Comment',
                                       int(comment_id),
                                       parent=blog_key())
                c = db.get(key)
                if c and self.user.key().id() != c.user_id:
                    # handle case
                    return self.redirect('/login')
                c.comment = comment
                c.put()
                self.redirect('/blog/%s' % post_id)
            else:
                error = "subject and content, please!"
                return self.render("editpost.html",
                                   subject=subject,
                                   content=content,
                                   error=error)

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')


def valid_email(email):
    return not email or EMAIL_RE.match(email)


class Signup(BlogHandler):
    def get(self):
        return self.render("signup-form.html")

    def post(self):
        """
            Sign up validation checkup.
        """
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username,
                      email=self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Register(Signup):
    def done(self):
        # Make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists please choose different username.'
            self.render('signup-form.html', error_username=msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/')


class Login(BlogHandler):
    def get(self):
        self.render('login-form.html', error=self.request.get('error'))

    def post(self):
        """
            Login validation.
        """
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error=msg)


class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/')


app = webapp2.WSGIApplication([
                               ('/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/deletepost/([0-9]+)', DeletePost),
                               ('/blog/editpost/([0-9]+)', EditPost),
                               ('/blog/deletecomment/([0-9]+)/([0-9]+)',
                                DeleteComment),
                               ('/blog/editcomment/([0-9]+)/([0-9]+)',
                                EditComment),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ],
                              debug=True)

""" Console scripts """
import getpass
from passlib.hash import sha256_crypt  # pylint: disable=E0611


def gen_password():
    """ Generate a salted password """
    password = getpass.getpass()
    verify = getpass.getpass()
    if password != verify:
        print "Passwords do not match!"
    else:
        print sha256_crypt.encrypt(password)

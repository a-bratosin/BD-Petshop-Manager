from flask import session


def is_customer_session():
    return session.get('loggedin') and session.get('role') == 'customer'


def allow_customer_or_guest():
    if session.get('loggedin'):
        return session.get('role') == 'customer'
    return True

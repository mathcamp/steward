""" Unit tests for param helpers """
import time
from datetime import datetime

import json
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.testing import DummyRequest
from unittest import TestCase

from steward import _param, argify


class TestParam(TestCase):
    """ Tests for the request.param utility """
    def test_unicode_param(self):
        """ Pull unicode params off of request object """
        request = DummyRequest()
        request.params = {'field': u'myfield'}
        field = _param(request, 'field')
        self.assertEquals(field, u'myfield')
        self.assertTrue(isinstance(field, unicode))

    def test_str_param(self):
        """ Pull binary string param off of request object """
        request = DummyRequest()
        request.params = {'field': u'myfield'}
        field = _param(request, 'field', type=str)
        self.assertEquals(field, 'myfield')
        self.assertTrue(isinstance(field, str))

    def test_list_param(self):
        """ Pull encoded lists off of request object """
        request = DummyRequest()
        request.params = {'field': json.dumps([1, 2, 3])}
        field = _param(request, 'field', type=list)
        self.assertEquals(field, [1, 2, 3])

    def test_dict_param(self):
        """ Pull encoded lists off of request object """
        request = DummyRequest()
        request.params = {'field': json.dumps({'a': 'b'})}
        field = _param(request, 'field', type=dict)
        self.assertEquals(field, {'a': 'b'})

    def test_datetime_param(self):
        """ Pull datetime off of request object """
        request = DummyRequest()
        now = int(time.time())
        request.params = {'field': now}
        field = _param(request, 'field', type=datetime)
        self.assertEquals(time.mktime(field.timetuple()), now)

    def test_bool_param(self):
        """ Pull bool off of request object """
        request = DummyRequest()
        request.params = {'field': 'true'}
        field = _param(request, 'field', type=bool)
        self.assertTrue(field is True)

    def test_missing_param(self):
        """ Raise HTTPBadRequest if param is missing """
        request = DummyRequest()
        request.params = {}
        request.json_body = {}
        myvar = object()
        field = _param(request, 'field', default=myvar)
        self.assertTrue(field is myvar)

    def test_default_param(self):
        """ Return default value if param is missing """
        request = DummyRequest()
        request.params = {}
        request.json_body = {}
        self.assertRaises(HTTPBadRequest, _param, request, 'field')

    def test_unicode_json_body(self):
        """ Pull unicode params out of json body """
        request = DummyRequest()
        request.params = {}
        request.json_body = {'field': u'myfield'}
        field = _param(request, 'field')
        self.assertEquals(field, u'myfield')
        self.assertTrue(isinstance(field, unicode))

    def test_str_json_body(self):
        """ Pull str params out of json body """
        request = DummyRequest()
        request.params = {}
        request.json_body = {'field': u'myfield'}
        field = _param(request, 'field', type=str)
        self.assertEquals(field, 'myfield')
        self.assertTrue(isinstance(field, str))

    def test_list_json_body(self):
        """ Pull list params out of json body """
        request = DummyRequest()
        request.params = {}
        request.json_body = {'field': [1, 2, 3]}
        field = _param(request, 'field', type=list)
        self.assertEquals(field, [1, 2, 3])

    def test_dict_json_body(self):
        """ Pull dict params out of json body """
        request = DummyRequest()
        request.params = {}
        request.json_body = {'field': {'a': 'b'}}
        field = _param(request, 'field', type=dict)
        self.assertEquals(field, {'a': 'b'})

    def test_datetime_json_body(self):
        """ Pull datetime params out of json body """
        request = DummyRequest()
        request.params = {}
        now = int(time.time())
        request.json_body = {'field': now}
        field = _param(request, 'field', type=datetime)
        self.assertEquals(time.mktime(field.timetuple()), now)


    def test_bool_json_body(self):
        """ Pull bool params out of json body """
        request = DummyRequest()
        request.params = {}
        request.json_body = {'field': True}
        field = _param(request, 'field', type=bool)
        self.assertTrue(field is True)

# pylint: disable=E1120,W0613,C0111

class TestArgify(TestCase):
    """ Tests for the argify decorator """
    def test_unicode(self):
        """ Pull unicode parameters from request """
        @argify
        def base_req(request, field):
            return field
        context = object()
        request = DummyRequest()
        request.params = {'field': u'myfield'}
        val = base_req(context, request)
        self.assertEquals(val, 'myfield')

    def test_missing(self):
        """ Raise exception if positional arg is missing """
        @argify
        def req(request, field):
            pass
        context = object()
        request = DummyRequest()
        request.params = {}
        request.json_body = {}
        self.assertRaises(HTTPBadRequest, req, context, request)

    def test_default(self):
        """ Don't raise exception if keyword arg is missing """
        @argify
        def req(request, field='myfield'):
            self.assertEquals(field, 'myfield')
        context = object()
        request = DummyRequest()
        request.params = {}
        request.json_body = {}
        req(context, request)

    def test_bool(self):
        """ Pull bool from request automatically """
        @argify(field=bool)
        def req(request, field):
            self.assertTrue(field is True)
        context = object()
        request = DummyRequest()
        request.params = {'field': 'True'}
        req(context, request)

    def test_list(self):
        """ Pull list from request automatically """
        @argify(field=list)
        def req(request, field):
            self.assertEquals(field, [1, 2, 3])
        context = object()
        request = DummyRequest()
        request.params = {'field': json.dumps([1, 2, 3])}
        req(context, request)

    def test_no_alter_if_test(self):
        """ args & kwargs unchanged if called from a test """
        @argify(field=list)
        def req(request, field):
            self.assertEquals(field, [1, 2, 3])
        request = DummyRequest()
        req(request, [1, 2, 3])

    def test_error_on_mismatch(self):
        """ argify throws error if there's an argument mismatch """
        def req(request, field):
            pass
        decorator = argify(foobar=bool)
        self.assertRaises(TypeError, decorator, req)

    def test_kwargs(self):
        """ argify will pass extra kwargs in **kwargs """
        @argify
        def req(request, f1, f2=None, **kwargs):
            self.assertEquals(f1, 'bar')
            self.assertEquals(kwargs, {'foobar': 'baz'})
        context = object()
        request = DummyRequest()
        request.params = {
            'f1': 'bar',
            'foobar': 'baz',
        }
        req(context, request)

    def test_kwargs_json_body(self):
        """ argify will pass extra kwargs in **kwargs in json body """
        @argify
        def req(request, f1, f2=None, **kwargs):
            self.assertEquals(f1, 'bar')
            self.assertEquals(kwargs, {'foobar': 'baz'})
        context = object()
        request = DummyRequest()
        request.params = {}
        request.json_body = {
            'f1': 'bar',
            'foobar': 'baz',
        }
        req(context, request)

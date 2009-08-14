#!/usr/bin/env python

"""
   gateway tests - Connection methods

   Copyright 2009 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

import unittest
import omero
import Ice
import test.gateway.library as lib

class ConnectionMethodsTest (lib.GTest):
    def testMultiProcessSession (self):
        #120 amongst other things trying to getSession() twice for the same session dies. Also in separate processes.
        # we mimic this by calling setGroupForSession, which calls sessionservice.getSession, 2 times on cloned connections
        self.loginAsAuthor()
        self.assertNotEqual(self.gateway._session, None)
        c2 = self.gateway.clone()
        self.assert_(c2.connect(sUuid=self.gateway._sessionUuid))
        self.assertEqual(c2._session, None)
        a = c2.getAdminService()
        g = omero.gateway.ExperimenterGroupWrapper(c2, a.containedGroups(c2._userid)[-1])
        self.assertNotEqual(g.name, c2.getEventContext().groupName)
        c2.setGroupForSession(g)
        c3 = self.gateway.clone()
        self.assert_(c3.connect(sUuid=self.gateway._sessionUuid))
        self.assertEqual(c3._session, None)
        a = c3.getAdminService()
        g = omero.gateway.ExperimenterGroupWrapper(c3, a.containedGroups(c3._userid)[1])
        self.assertNotEqual(g.name, c3.getEventContext().groupName)
        c3.setGroupForSession(g)

    def testSeppuku (self):
        self.loginAsAuthor()
        self.assertNotEqual(self.getTestImage(), None)
        self.gateway.seppuku()
        self.assertRaises(Ice.ConnectionLostException, self.getTestImage)
        self._has_connected = False
        self.doDisconnect()
        self.loginAsAuthor()
        self.assertNotEqual(self.getTestImage(), None)
        self.gateway.seppuku(softclose=False)
        self.assertRaises(Ice.ConnectionLostException, self.getTestImage)
        self._has_connected = False
        self.doDisconnect()

    def testTopLevelObjects (self):
        ##
        # Test listProjects as root (sees, does not own)
        self.loginAsAdmin()
        parents = self.getTestImage().getAncestry()
        project_id = parents[-1].getId()
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=False))
        self.assert_(project_id in ids)
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=True))
        self.assert_(project_id not in ids)
        ##
        # Test listProjects as author (sees, owns)
        self.loginAsAuthor()
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=False))
        self.assert_(project_id in ids)
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=True))
        self.assert_(project_id in ids)
        ##
        # Test listProjects as guest (does not see, does not own)
        self.doLogin(self.USER)
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=False))
        self.assert_(project_id not in ids)
        ids = map(lambda x: x.getId(), self.gateway.listProjects(only_owned=True))
        self.assert_(project_id not in ids)
        ##
        # Test getProject
        self.loginAsAuthor()
        self.assertEqual(self.gateway.getProject(project_id).getId(), project_id)
        ##
        # Test getDataset
        dataset_id = parents[0].getId()
        self.assertEqual(self.gateway.getDataset(dataset_id).getId(), dataset_id)
        ##
        # Test listExperimenters
        exps = map(lambda x: x.omeName, self.gateway.listExperimenters())
        for omeName in (self.USER.name, self.AUTHOR.name, self.ADMIN.name.decode('utf-8')):
            self.assert_(omeName in exps)
            self.assert_(len(list(self.gateway.listExperimenters(omeName))) > 0)
        self.assert_(len(list(self.gateway.listExperimenters(self.USER.name+self.AUTHOR.name+self.ADMIN.name))) ==  0)
        ##
        # Test lookupExperimenter
        self.assertEqual(self.gateway.lookupExperimenter(self.USER.name).omeName, self.USER.name)
        self.assertEqual(self.gateway.lookupExperimenter(self.USER.name+self.AUTHOR.name+self.ADMIN.name), None)
        ##
        # still logged in as Author, test listImages(ns)
        ns = 'weblitz.test_annotation'
        obj = self.getTestImage()
        # Make sure it doesn't yet exist
        obj.removeAnnotations(ns)
        self.assertEqual(obj.getAnnotation(ns), None)
        # Check without the ann
        self.assertEqual(len(list(self.gateway.listImages(ns=ns))), 0)
        annclass = omero.gateway.CommentAnnotationWrapper
        # createAndLink
        annclass.createAndLink(target=obj, ns=ns, val='foo')
        imgs = list((self.gateway.listImages(ns=ns)))
        self.assertEqual(len(imgs), 1)
        self.assertEqual(imgs[0], obj)
        # and clean up
        obj.removeAnnotations(ns)
        self.assertEqual(obj.getAnnotation(ns), None)

    def testCloseSession (self):
        #74 the failed connection for a user not in the system group does not get closed
        self.gateway.setIdentity(self.USER.name, self.USER.passwd)
        setprop = self.gateway.c.ic.getProperties().setProperty
        map(lambda x: setprop(x[0],str(x[1])), self.gateway._ic_props.items())
        self.gateway.c.ic.getImplicitContext().put(omero.constants.GROUP, self.gateway.group)
        self.assertEqual(self.gateway._sessionUuid, None)
        self.assertRaises(omero.SecurityViolation, self.gateway._createSession)
        self.assertNotEqual(self.gateway._sessionUuid, None)
        #74 bug found while fixing this, the uuid passed to closeSession was not wrapped in rtypes, so logout didn't
        self.gateway._closeSession() # was raising ValueError

        
    def testMiscellaneous (self):
        self.loginAsUser()
        self.assertEqual(self.gateway.getUser().omeName, self.USER.name)

if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
from sqlalchemy.orm import Session
from DB.Project import Project
from DB.ProjectPrivilege import ProjectPrivilege
from DB.Sample import Sample
from DB.Acquisition import Acquisition
from DB.Process import Process
from DB.Object import ObjectHeader, ObjectFields
from DB.Image import Image
from DB.Taxonomy import Taxonomy
from DB.User import User
import datetime
import json

SAMPLES_PER_PROJECT = 3
ACQ_PER_SAMPLE = 3
OBJS_PER_ACQ = 24
OBJECTS_IN_PROJECT = SAMPLES_PER_PROJECT*ACQ_PER_SAMPLE*OBJS_PER_ACQ


def do_load(session: Session):
    # Ensure we have a user and taxonomy for objects
    user = session.query(User).first()
    if not user:
        user = User(email="test@example.com", name="Test User", password="password", status=1)
        session.add(user)
        session.flush()

    taxo = session.query(Taxonomy).first()
    if not taxo:
        taxo = Taxonomy(id=1, name="Unclassified")
        session.add(taxo)
        session.flush()

    for i in range(3):
        # Create Project
        mapping_obj = {
            "area": "n01",
            "comment": "t01"
        }
        project = Project(
            title=f"Project {i}",
            instrument_id="UVP5",
            comments=f"Test project {i}",
            mappingobj=json.dumps(mapping_obj)
        )
        session.add(project)
        session.flush()

        # Grant manage rights to the user
        priv = ProjectPrivilege(projid=project.projid, member=user.id, privilege="Manage")
        session.add(priv)

        prj_id = project.projid

        for j in range(SAMPLES_PER_PROJECT):
            # Create Sample
            sample = Sample(
                projid=prj_id,
                orig_id=f"Sample_{i}_{j}",
                latitude=43.0 + i,
                longitude=7.0 + j
            )
            sample.set_next_pk(session, prj_id)
            session.add(sample)
            session.flush()

            for k in range(ACQ_PER_SAMPLE):
                # Create Acquisition
                acq = Acquisition(
                    acq_sample_id=sample.sampleid,
                    orig_id=f"Acq_{i}_{j}_{k}",
                    instrument="UVP5"
                )
                acq.set_next_pk(session, prj_id)
                session.add(acq)
                session.flush()

                # Create Process
                process = Process(
                    processid=acq.acquisid,
                    orig_id=f"Process_{i}_{j}_{k}"
                )
                session.add(process)
                
                # Create some Objects
                for l in range(OBJS_PER_ACQ):
                    obj_orig_id = f"Obj_{i}_{j}_{k}_{l}"
                    obj = ObjectHeader(
                        acquisid=acq.acquisid,
                        orig_id=obj_orig_id,
                        depth_min=500+l,
                        depth_max=1000+l,
                        objdate=datetime.date.today(),
                        objtime=datetime.time(12, 0, 0),
                        latitude=sample.latitude,
                        longitude=sample.longitude,
                        classif_id=taxo.id,
                        classif_qual='V' if l > 0 else None
                    )
                    obj.objid = ObjectHeader.get_next_pk(session, prj_id)
                    session.add(obj)
                    session.flush()
                    
                    # Create Object Fields
                    obj_fields = ObjectFields(
                        objfid=obj.objid,
                        acquis_id=acq.acquisid,
                        n01=10.5 * l,
                        t01=f"Comment {l}"
                    )
                    session.add(obj_fields)

                    # Create Image
                    img = Image(
                        objid=obj.objid,
                        imgrank=1,
                        width=100,
                        height=100,
                        orig_file_name=f"{obj_orig_id}.jpg",
                        thumb_width=50,
                        thumb_height=50
                    )
                    session.add(img)
    
    session.commit()

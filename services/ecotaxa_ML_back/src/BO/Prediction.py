# -*- coding: utf-8 -*-
# This file is part of Ecotaxa, see license.md in the application root directory for license informations.
# Copyright (C) 2015-2024  Picheral, Colin, Irisson (UPMC-CNRS), Amblard (LOVNOWER)
#

#
# A prediction is the output of an automatic classification process.
#    This is heavily based on machine learning algorithms.
#
from typing import Any, List, Dict, ClassVar

import numpy as np
from sqlalchemy import text, and_

from DB.Project import ProjectIDT
from DB.Object import ObjectIDT, ObjectHeader
# from DB.Acquisition import Acquisition
# from DB.Sample import Sample

from DB.CNNFeatureVector import (
    ObjectCNNFeatureVector,
    N_DEEP_FEATURES,
)
from DB.Image import Image
from DB.helpers import Session, Result
from helpers.DynamicLogs import get_logger

logger = get_logger(__name__)


class DeepFeatures(object):
    """
    ML predicting algorithm takes as input "features" which can be either input into EcoTaxa, and correspond
    to various measurements on the image and arbitrary data. @See ObjectFields.

    OTOH, it can also _generate_ features, using another class of machine learning algorithm: CNN
     @see https://en.wikipedia.org/wiki/Convolutional_neural_network
    These other features are stored in a dedicated DB table @see ObjectCNNFeatureVector.
    """

    SAVE_EVERY: ClassVar = 500

    # Deletion belongs to Web app
    # @staticmethod
    # def delete_all(session: Session, proj_id: ProjectIDT) -> int:
    #     """
    #     Delete all CNN features from DB, for this project.
    #     """
    #     sub_qry = session.query(ObjectHeader.objid)
    #     sub_qry = sub_qry.join(
    #         Acquisition, Acquisition.acquisid == ObjectHeader.acquisid
    #     )
    #     sub_qry = sub_qry.join(
    #         Sample,
    #         and_(
    #             Sample.sampleid == Acquisition.acq_sample_id, Sample.projid == proj_id
    #         ),
    #     )
    #     qry = session.query(ObjectCNNFeatureVector)
    #     qry = qry.filter(ObjectCNNFeatureVector.objcnnid.in_(sub_qry))
    #     nb_deleted = qry.delete(synchronize_session=False)
    #     return nb_deleted

    @staticmethod
    def find_missing(
        session: Session, proj_id: ProjectIDT, fast: bool = False
    ) -> Dict[ObjectIDT, str]:
        """
        Find missing cnn features for this project.
        :param fast: If set, do a fast check that some are absent, not listing them all.
                    Note: It _still_ takes a few seconds for millions of objects
        """
        sql = """
            SELECT obh.objid, img.imgid, img.orig_file_name
            FROM obj_head obh
            JOIN acquisitions acq ON acq.acquisid = obh.acquisid AND acq.acquisid <@ acq_in_prj(:proj_id)
            JOIN samples sam ON sam.sampleid = acq.acq_sample_id AND sam.projid = :proj_id
            LEFT JOIN images img ON img.objid = obh.objid
            LEFT JOIN obj_cnn_features_vector cnn ON cnn.objcnnid = obh.objid
            WHERE obh.objid <@ obj_in_prj(:proj_id)
              AND cnn.objcnnid IS NULL
        """
        if not fast:
            sql += " ORDER BY obh.objid, img.imgrank"
        if fast:
            # We don't need the whole list to check that some are missing
            sql += " LIMIT 10"

        res: Result = session.execute(text(sql), {"proj_id": proj_id})
        ret = {}
        for objid, imgid, orig_file_name in res:
            assert imgid is not None, "Object %d has no image in DB" % objid
            if objid not in ret:
                ret[objid] = Image.img_from_id_and_orig(imgid, orig_file_name)
            else:  # Only pick the first image
                pass
        return ret

    @classmethod
    def save(cls, session: Session, features: Any) -> int:
        """
        Insert CNN features to DB.
        Features is an iterable dict-like, a pandas dataframe for the moment.
        """
        nb_rows = 0
        bulks = []
        for obj_id, row in features.iterrows():
            bulks.append({"objcnnid": obj_id, "features": row.tolist()})
            nb_rows += 1
            if nb_rows % cls.SAVE_EVERY == 0:
                session.execute(ObjectCNNFeatureVector.__table__.insert(), bulks)
                bulks = []
        if bulks:
            session.execute(ObjectCNNFeatureVector.__table__.insert(), bulks)
        return nb_rows

    @classmethod
    def read_for_objects(
        cls, session: Session, oid_lst: List[int]
    ) -> Result:  # TODO: Should be ObjectIDListT
        """
        Read CNN lines AKA features, in order, for given object_ids
        """
        sql = """
            SELECT features
            FROM obj_cnn_features_vector
            JOIN UNNEST(:oids) WITH ORDINALITY AS ordr (objid, seq) ON objcnnid = ordr.objid
            ORDER BY ordr.seq
        """
        res: Result = session.execute(text(sql), {"oids": oid_lst})
        return res

    @classmethod
    def np_read_for_objects(cls, session: Session, oid_lst: List[int]) -> np.ndarray:
        """
        Read CNN lines AKA features, in order, for given object_ids, into a NumPy array
        """
        assert len(oid_lst) > 0, "No object_id given, maybe all objects are validated?"
        res = cls.read_for_objects(session, oid_lst)
        ret = np.empty(
            shape=(len(oid_lst), N_DEEP_FEATURES), dtype=np.float32
        )  # type: np.ndarray
        ndx = 0
        for a_row in res:
            all_feats = (
                a_row["features"].strip("[]").split(",")
                if type(a_row["features"]) == str
                else a_row["features"]
            )
            ret[ndx] = [float(x) for x in all_feats]
            ndx += 1
        assert ndx == len(
            oid_lst
        ), "Not enough CNN features in DB: expected %d read %d" % (len(oid_lst), ndx)
        return ret

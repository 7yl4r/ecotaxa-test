import logging
import pytest
import pandas as pd
import numpy as np

from sqlalchemy import and_

from API_operations.helpers.Service import Service
from BO.Prediction import DeepFeatures
from DB.CNNFeatureVector import ObjectCNNFeatureVector
from DB.Object import ObjectHeader
from DB.Acquisition import Acquisition
from DB.Sample import Sample
from data.db_load import OBJECTS_IN_PROJECT


def test_cnn_features_storage(database):
    prj_id = 1
    with Service() as sce:
        ret = DeepFeatures.find_missing(sce.session, prj_id)
        assert len(ret) == OBJECTS_IN_PROJECT
        obj_ids = list(ret.keys())

    # Prepare fake CNN features to insert
    features = []
    for i, oi in enumerate(obj_ids):
        features.append([(i + 1) * 0.1] * 50)
    features_df = pd.DataFrame(features, index=obj_ids)

    # Test features insertion
    with Service() as sce:
        n_inserts = DeepFeatures.save(sce.session, features_df)
        assert n_inserts == OBJECTS_IN_PROJECT
        sce.session.commit()

    # Test features retrieval
    with Service() as sce:
        ret_feats = DeepFeatures.np_read_for_objects(sce.session, obj_ids)
        assert (ret_feats == np.array(features, dtype="float32")).all()

    # Test find_missing without any missing features
    with Service() as sce:
        ret_missing = DeepFeatures.find_missing(sce.session, prj_id)
        assert ret_missing == {}

    # Test deletion
    with Service() as sce:
        # Delete all features manually, the deletion code is only in Web app
        sub_qry = sce.session.query(ObjectHeader.objid).join(
            Acquisition, Acquisition.acquisid == ObjectHeader.acquisid
        ).join(
            Sample, and_(Sample.sampleid == Acquisition.acq_sample_id, Sample.projid == prj_id)
        )
        n_deletes = sce.session.query(ObjectCNNFeatureVector).filter(
            ObjectCNNFeatureVector.objcnnid.in_(sub_qry)
        ).delete(synchronize_session=False)
        assert n_deletes == OBJECTS_IN_PROJECT
        sce.session.commit()

    # Test find_missing after deletion
    with Service() as sce:
        ret_missing_post = DeepFeatures.find_missing(sce.session, prj_id)
        assert len(ret_missing_post) == OBJECTS_IN_PROJECT

    # Test features retrieval for missing, should raise an error
    with Service() as sce:
        with pytest.raises(AssertionError):
            DeepFeatures.np_read_for_objects(sce.session, obj_ids)

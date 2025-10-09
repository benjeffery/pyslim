import json
import os
import random

import numpy as np
import pytest
import tskit

import pyslim
import tests
from .recipe_specs import recipe_eq


class TestProvenance(tests.PyslimTestCase):
    script_dir = os.path.dirname(os.path.realpath(__file__))

    def get_0_1_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.0.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.0.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_2_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.2.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.2.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_3_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.3.1.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.3.1.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_4_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.4.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.4.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_5_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.5.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.5.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_6_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.6.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.6.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_7_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v3.7.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v3.7.trees"),
        ]:
            yield tskit.load(filename)

    def get_0_8_slim_examples(self):
        for filename in [
            os.path.join(self.script_dir, "test_recipes", "recipe_WF.v4.2.2.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_WF_X.v4.2.2.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_WF_Y.v4.2.2.trees"),
            os.path.join(self.script_dir, "test_recipes", "recipe_nonWF.v4.2.2.trees"),
        ]:
            yield tskit.load(filename)

    def get_mixed_slim_examples(self):
        for filename in [
            os.path.join(
                self.script_dir, "test_recipes", "recipe_WF.v3.5_and_v3.6.trees"
            ),
        ]:
            yield tskit.load(filename)

    def test_provenance_creation(self):
        record = pyslim.make_pyslim_provenance_dict()
        tskit.provenance.validate_provenance(record)

    def verify_upgrade(self, ts):
        # check that we have successfully got read-able metadata
        # (since this isn't tested on load)
        tables = ts.tables
        for t in [
            tables.populations,
            tables.individuals,
            tables.nodes,
            tables.mutations,
        ]:
            ms = t.metadata_schema
            for x in t:
                _ = ms.validate_and_encode_row(x.metadata)

    def test_convert_0_1_files(self):
        for ts in self.get_0_1_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert record["model_type"] == pts.metadata["SLiM"]["model_type"]
            assert record["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_2_files(self):
        for ts in self.get_0_2_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_3_files(self):
        for ts in self.get_0_3_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_4_files(self):
        # Note that with version 0.5 and above, we *don't* get information from
        # provenance, we get it from top-level metadata
        for ts in self.get_0_4_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_5_files(self):
        for ts in self.get_0_5_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_6_files(self):
        for ts in self.get_0_6_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_7_files(self):
        for ts in self.get_0_7_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_0_8_files(self):
        for ts in self.get_0_8_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["tick"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            genome_type = None
            for n in samples:
                md = ts.node(n).metadata
                if not md["is_null"]:
                    genome_type = md["genome_type"]
                    break
            assert genome_type is not None
            chromosome_type = pts.metadata["SLiM"]["this_chromosome"]["type"]
            GENOME_TYPE_AUTOSOME = 0
            GENOME_TYPE_X = 1
            GENOME_TYPE_Y = 2
            if genome_type == GENOME_TYPE_AUTOSOME:
                assert chromosome_type == "A"
            elif genome_type == GENOME_TYPE_X:
                assert chromosome_type == "X"
            elif genome_type == GENOME_TYPE_Y:
                assert chromosome_type == "-Y"
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    def test_convert_mixed_files(self):
        for ts in self.get_mixed_slim_examples():
            assert not pyslim.is_current_version(ts)
            with pytest.warns(Warning):
                pts = pyslim.update(ts)
            assert pyslim.is_current_version(pts)
            self.verify_upgrade(pts)
            assert ts.num_provenances == 1
            assert pts.num_provenances == 2
            assert ts.provenance(0).record == pts.provenance(0).record
            record = json.loads(ts.provenance(0).record)
            assert isinstance(pts.metadata, dict)
            assert "SLiM" in pts.metadata
            assert (
                record["parameters"]["model_type"] == pts.metadata["SLiM"]["model_type"]
            )
            assert record["slim"]["generation"] == pts.metadata["SLiM"]["tick"]
            assert list(ts.samples()) == list(pts.samples())
            assert np.array_equal(ts.tables.nodes.flags, pts.tables.nodes.flags)
            samples = list(ts.samples())
            t = ts.first()
            pt = pts.first()
            for _ in range(20):
                u = random.sample(samples, 1)[0]
                assert t.parent(u) == pt.parent(u)
                if t.parent(u) != tskit.NULL:
                    assert t.branch_length(u) == pt.branch_length(u)

    @pytest.mark.parametrize("recipe", [next(recipe_eq())], indirect=True)
    def test_current_format(self, recipe):
        for _, ts in recipe["ts"].items():
            uts = pyslim.update(ts)
            ts.tables.assert_equals(uts.tables)

    def test_file_warnings(self):
        for ts in self.get_0_6_slim_examples():
            with pytest.warns(Warning, match="pyslim.update"):
                with pytest.raises(ValueError, match="top-level metadata"):
                    _ = pyslim.recapitate(ts, ancestral_Ne=10)
            with pytest.warns(Warning, match="pyslim.update"):
                with pytest.raises(KeyError, match="tick"):
                    _ = pyslim.slim_time(ts, 0)

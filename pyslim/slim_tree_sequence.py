import attr
import struct
import msprime
import tskit
import kastore
import json
from collections import OrderedDict
import warnings
import numpy as np

from .slim_metadata import *
from .provenance import *
from .util import *
from .slim_metadata import _decode_mutation_pre_nucleotides

INDIVIDUAL_ALIVE = 2**16
INDIVIDUAL_REMEMBERED = 2**17
INDIVIDUAL_FIRST_GEN = 2**18

# A nucleotide k in mutation metadata actually means
# something that in reference_sequence is NUCLEOTIDES[k]
NUCLEOTIDES = ['A', 'C', 'G', 'T']

def load(path):
    '''
    Load the SLiM-compatible tree sequence found in the .trees file at ``path``.

    :param string path: The path to a .trees file.
    '''
    ts = SlimTreeSequence.load(path)
    return ts


def load_tables(tables, **kwargs):
    '''
    See :func:`SlimTreeSequence.load_tables`.

    :param TableCollection tables: A set of tables.
    '''
    ts = SlimTreeSequence.load_tables(tables, **kwargs)
    return ts


def annotate_defaults(ts, model_type, slim_generation, reference_sequence=None):
    '''
    Takes a tree sequence (as produced by msprime, for instance), and adds in the
    information necessary for SLiM to use it as an initial state, filling in
    mostly default values. Returns a :class:`SlimTreeSequence`.

    :param TreeSequence ts: A :class:`TreeSequence`.
    :param string model_type: SLiM model type: either "WF" or "nonWF".
    :param int slim_generation: What generation number in SLiM correponds to
        ``time=0`` in the tree sequence.
    '''
    tables = ts.dump_tables()
    annotate_defaults_tables(tables, model_type, slim_generation)
    return SlimTreeSequence.load_tables(tables,
                reference_sequence=reference_sequence)


def annotate_defaults_tables(tables, model_type, slim_generation):
    '''
    Does the work of :func:`annotate_defaults()`, but modifies the tables in place: so,
    takes tables as produced by ``msprime``, and makes them look like the
    tables as output by SLiM. See :func:`annotate_defaults` for details.
    '''
    if (type(slim_generation) is not int) or (slim_generation < 1):
        raise ValueError("SLiM generation must be an integer and at least 1.")
    # set_nodes must come before set_populations
    if model_type == "WF":
        default_ages = -1
    elif model_type == "nonWF":
        default_ages = 0
    else:
        raise ValueError("Model type must be 'WF' or 'nonWF'")
    _set_nodes_individuals(tables, age=default_ages)
    _set_populations(tables)
    _set_sites_mutations(tables)
    _set_provenance(tables, model_type=model_type, slim_generation=slim_generation)


class SlimTreeSequence(tskit.TreeSequence):
    '''
    This is just like a :class:`tskit.TreeSequence`, with a few more properties
    and methods, including:

    - :attr:`.slim_generation` - the SLiM "generation" at the end of the simulation
    - :attr:`.reference_sequence` - if using a nucleotide model, the reference sequence
    - :attr:`.individual_locations` - numpy array of individual locations
    - :attr:`.individual_ages` - numpy array of individiual ages
    - :attr:`.individual_times` - numpy array of how long ago each individual was born
    - :attr:`.individual_populations` - numpy array of individual's populations

    All mutable properties of individuals (e.g., age) is as it was recorded during
    the individual's last time step alive (or at the end of the simulation, if they
    are still alive).

    You can create a :class:`.SlimTreeSequence` using one of

    - :meth:`.SlimTreeSequence.load_tables` :meth:`.SlimTreeSequence.load`,
    - :func:`.load`, or :func:`.load_tables`.

    :ivar slim_generation: The generation that the SLiM simulation was at upon writing;
        will be read from provenance if not provided.
    :ivar reference_sequence: None, or an string of length equal to the sequence
        length that gives the entire reference sequence for nucleotide models.
    :vartype slim_generation: int
    :vartype reference_sequence: string
    '''

    def __init__(self, ts, reference_sequence=None):
        provenance = get_provenance(ts)
        slim_generation = provenance.slim_generation
        if provenance.file_version != "0.4":
            warnings.warn("This is an version {} SLiM tree sequence.".format(provenance.file_version) +
                          " When you write this out, " +
                          "it will be converted to version 0.4.")
            tables = ts.dump_tables()
            if provenance.file_version == "0.1" or provenance.file_version == "0.2":
                # add empty nucleotide slots to metadata
                mut_bytes = tskit.unpack_bytes(tables.mutations.metadata,
                                               tables.mutations.metadata_offset)
                mut_metadata = [_decode_mutation_pre_nucleotides(md)
                                for md in mut_bytes]
                annotate_mutation_metadata(tables, mut_metadata)
            if provenance.file_version == "0.1":
                # shift times
                node_times = tables.nodes.time + slim_generation
                tables.nodes.set_columns(
                        flags=tables.nodes.flags,
                        time=node_times,
                        population=tables.nodes.population,
                        individual=tables.nodes.individual,
                        metadata=tables.nodes.metadata,
                        metadata_offset=tables.nodes.metadata_offset)
                migration_times = tables.migrations.time + slim_generation
                tables.migrations.set_columns(
                        left=tables.migrations.left,
                        right=tables.migrations.right,
                        node=tables.migrations.node,
                        source=tables.migrations.source,
                        dest=tables.migrations.dest,
                        time=migration_times)
            upgrade_slim_provenance(tables)
            ts = tables.tree_sequence()
            provenance = get_provenance(ts)
            assert(provenance.file_version == "0.4")
        super().__init__(ts._ll_tree_sequence)
        self.slim_generation = slim_generation
        self.reference_sequence = reference_sequence
        # pre-extract individual metadata
        self.individual_locations = ts.tables.individuals.location
        self.individual_locations.shape = (int(len(self.individual_locations)/3), 3)
        self.individual_ages = np.zeros(ts.num_individuals, dtype='int')
        if self.slim_provenance.model_type != "WF":
            self.individual_ages = np.fromiter(map(lambda ind: decode_individual(ind.metadata).age, ts.individuals()), dtype='int64')

        self.individual_times = np.zeros(ts.num_individuals)
        self.individual_populations = np.repeat(np.int32(-1), ts.num_individuals)
        if not np.all(unique_labels_by_group(ts.tables.nodes.individual,
                                              ts.tables.nodes.population)):
            raise ValueError("Individual has nodes from more than one population.")
        if not np.all(unique_labels_by_group(ts.tables.nodes.individual,
                                              ts.tables.nodes.time)):
            raise ValueError("Individual has nodes from more than one time.")
        has_indiv = (ts.tables.nodes.individual >= 0)
        which_indiv = ts.tables.nodes.individual[has_indiv]
        # if we did not do the sanity check above then an individual with nodes in more than one pop
        # would get the pop of their last node in the list
        self.individual_populations[which_indiv] = ts.tables.nodes.population[has_indiv]
        self.individual_times[which_indiv] = ts.tables.nodes.time[has_indiv]

    @classmethod
    def load(cls, path):
        '''
        Load a :class:`SlimTreeSequence` from a .trees file on disk.

        :param string path: The path to a .trees file.
        :rtype SlimTreeSequence:
        '''
        ts = tskit.load(path)
        # extract the reference sequence from the kastore
        kas = kastore.load(path)
        if 'reference_sequence/data' in kas:
            int_rs = kas['reference_sequence/data']
            reference_sequence = int_rs.tostring().decode('ascii')
        else:
            reference_sequence = None
        return cls(ts, reference_sequence)

    @classmethod
    def load_tables(cls, tables, **kwargs):
        '''
        Creates the :class:`SlimTreeSequence` defined by the tables.

        :param TableCollection tables: A set of tables, as produced by SLiM
            or by annotate_defaults().
        :param TableCollection reference_sequence: An optional string of ACGT giving
            the reference sequence.
        :rtype SlimTreeSequence:
        '''
        # a roundabout way to copy the tables
        ts = tables.tree_sequence()
        return cls(ts, **kwargs)

    def simplify(self, *args, **kwargs):
        '''
        This is a wrapper for :meth:`tskit.TreeSequence.simplify`.
        The only difference is that this method returns the
        derived class :class:`.SlimTreeSequence`.

        :rtype SlimTreeSequence:
        '''
        sts = super(SlimTreeSequence, self).simplify(*args, **kwargs)
        if (type(sts) == tuple):
            ret = (SlimTreeSequence(sts[0]), sts[1])
            ret[0].reference_sequence = self.reference_sequence
        else:
            ret = SlimTreeSequence(sts)
            ret.reference_sequence = self.reference_sequence

        return ret

    def population(self, id_):
        '''
        Returns the population whose ID is given by `id_`, as documented in
        :meth:`tskit.TreeSequence.population`, but with additional attributes::

            slim_id, selfing_fraction, female_cloning_fraction,
            male_cloning_fraction, sex_ratio,
            bounds_x0, bounds_x1, bounds_y0, bounds_y1, bounds_z0, bounds_z1,
            migration_records.

        These are all recorded by SLiM in the metadata.

        Note that SLiM populations are usually indexed starting from 1,
        but in tskit from zero, so there may be populations (e.g., with id_=0)
        that have no metadata and are not used by SLiM.

        :param int id_: The ID of the population (i.e., its index).
        '''
        pop = super(SlimTreeSequence, self).population(id_)
        try:
            pop.metadata = decode_population(pop.metadata)
        except:
            pass
        return pop

    def individual(self, id_):
        '''
        Returns the individual whose ID is given by `id_`, as documented in
        :meth:`tskit.TreeSequence.individual`, but with additional attributes::

          time, pedigree_id, age, slim_population, sex, slim_flags.

        The `time` and `population` properties are extracted from the nodes,
        and an error will be thrown if the individual's nodes derive from
        more than one population or more than one time.

        :param int id_: The ID of the individual (i.e., its index).
        '''
        ind = super(SlimTreeSequence, self).individual(id_)
        ind.population = self.individual_populations[id_]
        ind.time = self.individual_times[id_]
        try:
            ind.metadata = decode_individual(ind.metadata)
        except:
            pass
        return ind

    def node(self, id_):
        '''
        Returns the node whose ID is given by `id_`, as documented in
        :meth:`tskit.TreeSequence.node`, but with additional attributes::

           slim_id, is_null, genome_type.

        These are all recorded by SLiM in the metadata.

        :param int id_: The ID of the node (i.e., its index).
        '''
        node = super(SlimTreeSequence, self).node(id_)
        try:
            node.metadata = decode_node(node.metadata)
        except:
            pass
        return node

    def mutation(self, id_):
        '''
        Returns the mutation whose ID is given by `id_`, as documented in
        :meth:`tskit.TreeSequence.mutation`, but with additional attributes::

           mutation_type, selection_coeff, population, slim_time, nucleotide.

        These are all recorded by SLiM in the metadata.

        :param int id_: The ID of the mutation (i.e., its index).
        '''
        mut = super(SlimTreeSequence, self).mutation(id_)
        try:
            mut.metadata = decode_mutation(mut.metadata)
        except:
            pass
        return mut

    def recapitate(self, recombination_rate=None, keep_first_generation=False,
                   population_configurations=None, recombination_map=None, **kwargs):
        '''
        Returns a "recapitated" tree sequence, by using msprime to run a
        coalescent simulation from the "top" of this tree sequence, i.e.,
        allowing any uncoalesced lineages to coalesce.

        To allow recapitation to be done correctly, the individuals of the
        first generation of the SLiM simulation have been recorded in the tree
        sequence, but are not marked as samples. This method (or,
        :meth:`.simplify()`) will remove any non-samples that are not needed to
        describe the resulting trees, so if you want to keep them you must set
        ``keep_first_generation`` to True.

        This also means that you must *not* simplify before you recapitate your
        SLiM-produced tree sequence.

        Note that ``Ne`` is not set automatically, so defaults to ``1.0``; you probably
        want to set it explicitly.  Similarly, migration is not set up
        automatically, so that if there are uncoalesced lineages in more than
        one population, you will need to pass in a migration matrix to allow
        coalescence. In both cases, remember that population IDs in ``tskit`` begin
        with 0, so that if your SLiM simulation has populations ``p1`` and ``p2``,
        then the tree sequence will have three populations (but with no nodes
        assigned to population 0), so that migration rate of 1.0 between ``p1`` and
        ``p2`` needs a migration matrix of::

           [[0.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]]

        In general, all defaults are whatever the defaults of ``msprime.simulate`` are;
        this includes recombination rate, so that if neither ``recombination_rate``
        or a ``recombination_map`` are provided, there will be *no* recombination.

        However, if ``recombination_rate`` *is* provided, then recapitation will
        use a constant rate of recombination on a discretized map -- in other words,
        recombinations in the coalescent portion of the simulation will only occur
        at integer locations, just as in SLiM. If you do not want this to happen,
        you need to construct a ``recombination_map`` explicitly.

        :param float recombination_rate: A (constant) recombination rate,
            in units of crossovers per nucleotide per unit of time.
        :param bool keep_first_generation: Whether to keep the individuals (and genomes)
            corresponding to the first SLiM generation in the resulting tree sequence
        :param list population_configurations: See :meth:`msprime.simulate` for
            this argument; if not provided, each population will have zero growth rate
            and the same effective population size.
        :type recombination_map: :class`msprime.RecombinationMap`
        :param recombination_map: The recombination map, or None,
            if recombination_rate is specified.
        :param dict kwargs: Any other arguments to :meth:`msprime.simulate`.
        '''
        if recombination_rate is not None:
            if recombination_map is not None:
                raise ValueError("Cannot specify length/recombination_rate along with a recombination map")
            # temporary hack to deal with old msprime
            if hasattr(msprime.RecombinationMap, "discrete"):
                recombination_map = msprime.RecombinationMap(positions = [0.0, self.sequence_length],
                                                             rates = [recombination_rate, 0.0],
                                                             discrete=True)
            else:
                recombination_map = msprime.RecombinationMap(positions = [0.0, self.sequence_length],
                                                             rates = [recombination_rate, 0.0],
                                                             num_loci = int(self.sequence_length))

        if population_configurations is None:
            population_configurations = [msprime.PopulationConfiguration()
                                         for _ in range(self.num_populations)]

        if keep_first_generation:
            ts = self._mark_first_generation()
        else:
            ts = self

        recap = msprime.simulate(
                    from_ts = ts,
                    population_configurations = population_configurations,
                    recombination_map = recombination_map,
                    start_time = self.slim_generation,
                    **kwargs)
        ts = SlimTreeSequence.load_tables(recap.tables)
        ts.reference_sequence = self.reference_sequence
        return ts

    def mutation_at(self, node, position, time=None):
        '''
        Finds the mutation present in the genome of ``node`` at ``position``,
        returning -1 if there is no such mutation recorded in the tree
        sequence.  Warning: if ``node`` is not actually in the tree sequence
        (e.g., not ancestral to any samples) at ``position``, then this
        function will return -1, possibly erroneously.  If `time` is provided,
        returns the last mutation at ``position`` inherited by ``node`` that
        occurred at or before ``time`` ago (using the `slim_time` attribute of
        mutation metadata to infer this).

        :param int node: The index of a node in the tree sequence.
        :param float position: A position along the genome.
        :param int time: The time ago that we want the nucleotide, or None,
            in which case the ``time`` of ``node`` is used.

        :returns: Index of the mutation in question, or -1 if none.
        '''
        if position < 0 or position >= self.sequence_length:
            raise ValueError("Position {} not valid.".format(position))
        if node < 0 or node >= self.num_nodes:
            raise ValueError("Node {} not valid.".format(node))
        if time is None:
            time = self.node(node).time
        tree = self.at(position)
        # TODO: use mutation.time when this is available:
        slim_time = self.slim_generation - time
        # tskit time-ago begins at generation slim_generation - 1
        # in WF models when the tree sequence is saved out in early
        if self.slim_provenance.model_type == "WF":
            time_adjust = (self.slim_generation
                    - self.individual(self.first_generation_individuals()[0]).time)
            slim_time -= time_adjust
        site_pos = self.tables.sites.position
        out = tskit.NULL
        if position in site_pos:
            site_index = np.where(site_pos == position)[0][0]
            site = self.site(site_index)
            mut_nodes = []
            # look for only mutations that occurred before `time`
            # not strictly necessary if time was None
            for mut in site.mutations:
                if len(mut.metadata) == 0:
                    raise ValueError("All mutations must have SLiM metadata.")
                if max([u.slim_time for u in mut.metadata]) <= slim_time:
                    mut_nodes.append(mut.node)
            n = node
            while n > -1 and n not in mut_nodes:
                n = tree.parent(n)
            if n >= 0:
                # do careful error checking here
                for mut in site.mutations:
                    if mut.node == n:
                        assert(out == tskit.NULL or out == mut.parent)
                        out = mut.id
        return out

    def nucleotide_at(self, node, position, time=None):
        '''
        Finds the nucleotide present in the genome of ``node`` at ``position``.
        Warning: if ``node`` is not actually in the tree sequence (e.g., not
        ancestral to any samples) at ``position``, then this function will
        return the reference sequence nucleotide, possibly erroneously.  If
        `time` is provided, returns the last nucletide produced by a mutation
        at ``position`` inherited by ``node`` that occurred at or before
        ``time`` ago (using the `slim_time` attribute of mutation metadata
        to infer this).

        :param int node: The index of a node in the tree sequence.
        :param float position: A position along the genome.
        :param int time: The time ago that we want the nucleotide, or None,
            in which case the ``time`` of ``node`` is used.

        :returns: Index of the nucleotide in ``NUCLEOTIDES`` (0=A, 1=C, 2=G, 3=T).
        '''
        if self.reference_sequence is None:
            raise ValueError("This tree sequence has no reference sequence.")
        mut_id = self.mutation_at(node, position, time)
        if mut_id == tskit.NULL:
            out = NUCLEOTIDES.index(self.reference_sequence[int(position)])
        else:
            mut = self.mutation(mut_id)
            k = np.argmax([u.slim_time for u in mut.metadata])
            out = mut.metadata[k].nucleotide
        return out

    @property
    def slim_provenance(self):
        '''
        Returns model type, slim generation, and remembmered node count from
        the last entry in the provenance table that is tagged with "program"="SLiM".

        :rtype ProvenanceMetadata:
        '''
        return get_provenance(self, only_last=True)

    @property
    def slim_provenances(self):
        '''
        Returns model type, slim generation, and remembmered node count from *all*
        entries in the provenance table that is tagged with "program"="SLiM"

        :rtype ProvenanceMetadata:
        '''
        return get_provenance(self, only_last=False)

    def _mark_first_generation(self):
        '''
        Mark all 'first generation' individuals' nodes as samples, and return
        the corresponding tree sequence.
        '''
        tables = self.dump_tables()
        first_gen_nodes = ((tables.nodes.individual > 0)
                           & ((tables.individuals.flags[tables.nodes.individual]
                               & INDIVIDUAL_FIRST_GEN) > 0))
        if sum(first_gen_nodes) == 0:
            warnings.warn("Tree sequence does not have the initial generation; " +
                          " did you simplify it after output from SLiM?")
        flags = tables.nodes.flags
        flags[first_gen_nodes] = (flags[first_gen_nodes] | tskit.NODE_IS_SAMPLE)
        tables.nodes.set_columns(flags=flags, population=tables.nodes.population,
                individual=tables.nodes.individual, time=tables.nodes.time,
                metadata=tables.nodes.metadata,
                metadata_offset=tables.nodes.metadata_offset)
        ts = load_tables(tables)
        ts.reference_sequence = self.reference_sequence
        return ts

    def individuals_alive_at(self, time, stage='late', remembered_stage='late'):
        """
        Returns an array giving the IDs of all individuals that are known to be
        alive at the given time ago.  This is determined using their birth time
        ago (given by their `time` attribute) and, for nonWF models,
        their `age` attribute (which is equal to their age at the last time
        they were Remembered). See also :meth:`.individual_ages_at`.

        In WF models, birth occurs after "early()", so that individuals are only
        alive during "late()" for the time step when they have age zero,
        while in nonWF models, birth occurs before "early()", so they are alive
        for both stages.
        
        In both WF and nonWF models, mortality occurs between
        "early()" and "late()", so that individuals are last alive during the
        "early()" stage of the time step of their final age, and if individuals
        are alive during "late()" they will also be alive during "early()" of the
        next time step. This means it is important to know during which stage
        individuals were Remembered - for instance, if the call to
        sim.treeSeqRememberIndividuals() was made during "early()" of a given time step,
        then those individuals might not have survived until "late()" of that
        time step. Since SLiM does not record the stage at which individuals
        were Remembered, you can specify this by setting ``remembered_stages``:
        it should be the stage during which *all* calls to sim.treeSeqRememberIndividuals,
        as well as to sim.treeSeqOutput(), were made.

        Note also that in nonWF models, birth occurs before "early()", so the
        possible parents in a given time step are those that are alive in
        "early()" and have age greater than zero, or, equivalently, are alive in
        "late()" during the previous time step.
        In WF models, birth occurs after "early()", so possible parents in a
        given time step are those that are alive during "early()" of that time
        step or are alive during "late()" of the previous time step.

        :param float time: The number of time steps ago.
        :param str stage: The stage in the SLiM life cycle that we are inquiring
            about (either "early" or "late"; defaults to "late").
        :param str remembered_stage: The stage in the SLiM life cycle that
            individuals were Remembered during.
        """
        if stage not in ("late", "early"):
            raise ValueError(f"Unknown stage '{stage}': "
                              "should be either 'early' or 'late'.")
        if remembered_stage not in ("late", "early"):
            raise ValueError(f"Unknown stage '{remembered_stage}': "
                              "should be either 'early' or 'late'.")
        # sanity check "remembered_stage" (only possible for WF models)
        if self.slim_provenance.model_type == "WF":
            first_gen = self.first_generation_individuals()
            if len(first_gen) > 0:
                dt = (self.slim_generation
                        - self.individual(first_gen[0]).time)
                if (dt == 0) != (remembered_stage == "late"):
                    warnings.warn("It looks like the tree sequence was not saved to file "
                            f"during remembered_stage={remembered_stage}. "
                            "This may cause inaccuracies in deciding which individuals "
                            "are alive at what times.")

        # birth_time is the time ago that they were first alive in 'late'
        # in a nonWF model they are alive for the same time step's 'early'
        # but in a WF model the first 'early' they were alive for is one more recent
        birth_time = self.individual_times
        # birth_time - birth_offset is the first time ago they were alive
        # during stage 'stage'
        if stage == "early" and self.slim_provenance.model_type == "WF":
            birth_offset = 1
        else:
            birth_offset = 0
        # ages is the number of complete life cycles they are known to have lived through,
        # and so individuals have lived through at least 'age + 1' of both stages.
        # In nonWF models, they live for one more 'early' than 'late',
        # but this is only reflected in their age if Remembered in 'early'.
        ages = self.individual_ages
        # ages + age_offset + 1 is the number of 'stage' stages they are known
        # to have lived through
        if (self.slim_provenance.model_type == "WF"
                or stage == remembered_stage):
            age_offset = 0
        else:
            if (remembered_stage == "early"
                    and stage == "late"):
                age_offset = -1
            else:
                age_offset = 1
        # if adjusted age=0 then they are be alive at exactly one time step
        alive_bool = np.logical_and(
                birth_time >= time + birth_offset,
                birth_time - ages <= time + birth_offset + age_offset)
        return np.where(alive_bool)[0]

    def individual_ages_at(self, time, stage="late", remembered_stage="late"):
        """
        Returns the *ages* of each individual at the corresponding time ago,
        which will be `nan` if the individual is either not born yet or dead.
        This is computed as the time ago the individual was born (found by the
        `time` associated with the the individual's nodes) minus the `time`
        argument; while "death" is inferred from the individual's `age`,
        recorded in metadata. These values are the same as what would be shown
        in SLiM during the corresponding time step and stage.

        Since age increments at the end of each time step,
        the age is the number of time steps ends the individual has lived
        through, so if they were born in time step `time`, then their age
        will be zero.

        In a WF model, this method does not provide any more information than
        does :meth:`.individuals_alive_at`, but for consistency, non-nan ages
        will be 0 in "late" and 1 in "early".
        See :meth:`.individuals_alive_at` for further discussion.

        :param float time: The reference time ago.
        :param str stage: The stage in the SLiM life cycle used to determine who
            is alive (either "early" or "late"; defaults to "late").
        :param str remembered_stage: The stage in the SLiM life cycle that
            individuals were Remembered during.
        """
        ages = np.repeat(np.nan, self.num_individuals)
        alive = self.individuals_alive_at(time, stage=stage,
                                          remembered_stage=remembered_stage)
        ages[alive] = self.individual_times[alive] - time
        return ages

    def first_generation_individuals(self):
        """
        Returns the IDs of the individuals remembered as part of the first SLiM generation,
        as determined by their flags.
        """
        return np.where(self.tables.individuals.flags & INDIVIDUAL_FIRST_GEN > 0)[0]

    def has_individual_parents(self, remembering_stage="late"):
        '''
        Finds which individuals have both their parent individuals also present
        in the tree sequence, as far as we can tell. To do this, we return the
        IDs of individuals for which:

        - all edges terminating in that individual's nodes are in individuals,
        - each of the individual's nodes inherit from a single individual only,
        - those parental individuals were alive when the individual was born,
        - the parental individuals account for two whole genomes.

        This returns a boolean array indicating for each individual whether all
        these are true.

        See :meth:`.individuals_alive_at` for further discussion about how
        this is determined based on when the individuals were Remembered.

        :return: A boolean array of length equal to ``targets``.
        '''
        edges = self.tables.edges
        nodes = self.tables.nodes
        edge_parent_indiv = nodes.individual[edges.parent]
        edge_child_indiv = nodes.individual[edges.child]
        # nodes whose parent nodes are all in the same individual
        unique_parent_nodes = unique_labels_by_group(
                edges.child,
                edge_parent_indiv,
                minlength=nodes.num_rows)
        unique_parent_edges = unique_parent_nodes[edges.child]
        # edges describing relationships between individuals
        indiv_edges = np.logical_and(
                np.logical_and(edge_parent_indiv != tskit.NULL,
                                     edge_child_indiv != tskit.NULL),
                unique_parent_edges)
        # individual edges where the parent was alive during "late"
        # of the time step before the child is born
        child_births = self.individual_times[edge_child_indiv[indiv_edges]]
        parent_births = self.individual_times[edge_parent_indiv[indiv_edges]]
        alive_edges = indiv_edges.copy()
        if self.slim_provenance.model_type == "WF":
            alive_edges[indiv_edges] = (child_births + 1 == parent_births)
        else:
            parent_deaths = parent_births - self.individual_ages[edge_parent_indiv[indiv_edges]]
            alive_edges[indiv_edges] = (child_births + 1 >= parent_deaths)
        # total genome inherited from parents
        edge_spans = edges.right - edges.left
        parental_span = np.bincount(edge_child_indiv[alive_edges],
                weights=edge_spans[alive_edges], minlength=self.num_individuals)
        # we could also check for edges without individual parents terminating
        # in this individual, but this is unnecessary as the entire genome is
        # accounted for
        has_all_parents = (parental_span == 2 * self.sequence_length)
        return has_all_parents

def _set_nodes_individuals(
        tables, node_ind=None, location=(0, 0, 0), age=0, ind_id=None,
        ind_population=None, ind_sex=INDIVIDUAL_TYPE_HERMAPHRODITE,
        ind_flags=INDIVIDUAL_ALIVE, slim_ind_flags=0, node_id=None,
        node_is_null=False, node_type=GENOME_TYPE_AUTOSOME):
    '''
    Adds to a TableCollection the information relevant to individuals required
    for SLiM to load in a tree sequence, that is found in Node and Individual
    tables.  This will replace any existing Individual table, and will replace
    any information already in the individual, metadata, and population columns
    of the Node table.

    This is designed to make it easy to assign default values:
    - (node_ind) the 2*j-th and (2*j+1)-st `sample` nodes to individual j
    - (location) individual locations to (0, 0, 0)
    - (age) individual age to 0
    - (ind_id) SLiM individual pedigree IDs to sequential integers starting from 0
    - (ind_population) individual populations to 0
    - (node_id) SLiM genome IDs to sequential integers starting with samples from 0
    - (node_is_null) genomes to be non-null
    - (node_type) genome type to 0 (= autosome)
    - (ind_flags) INDIVIDUAL_ALIVE

    If you have other situations, like non-alive "remembered" individuals, you
    will need to edit the tables by hand, afterwards.
    '''
    samples = list(filter(lambda j: tables.nodes.flags[j] & tskit.NODE_IS_SAMPLE,
                          range(tables.nodes.num_rows)))
    if (len(samples) % 2) != 0:
        raise ValueError("There must be an even number of sampled nodes,"\
                         + "since organisms are diploid.")

    if node_ind is None:
        node_ind = [tskit.NULL for _ in range(tables.nodes.num_rows)]
        for j, k in enumerate(samples):
            node_ind[j] = int(k/2)

    num_individuals = max(node_ind) + 1
    num_nodes = tables.nodes.num_rows

    if type(location) is tuple:
        location = [location for _ in range(num_individuals)]
    assert(len(location) == num_individuals)

    if type(age) is int or type(age) is float:
        age = [age for _ in range(num_individuals)]
    assert(len(age) == num_individuals)

    if ind_id is None:
        ind_id = list(range(num_individuals))
    assert(len(ind_id) == num_individuals)

    if type(ind_sex) is int:
        ind_sex = [ind_sex for _ in range(num_individuals)]
    assert(len(ind_sex) == num_individuals)

    if type(slim_ind_flags) is int:
        slim_ind_flags = [slim_ind_flags for _ in range(num_individuals)]
    assert(len(slim_ind_flags) == num_individuals)

    if type(ind_flags) is int:
        ind_flags = [ind_flags for _ in range(num_individuals)]
    assert(len(ind_flags) == num_individuals)

    if node_id is None:
        node_id = [-1 for _ in range(num_nodes)]
        for j, k in enumerate(list(samples)
                              + sorted(list(set(range(num_nodes))
                                            - set(samples)))):
            node_id[k] = j
    assert(len(node_id) == num_nodes)

    if type(node_is_null) is bool:
        node_is_null = [node_is_null for _ in range(num_nodes)]
    assert(len(node_is_null) == num_nodes)

    if type(node_type) is int:
        node_type = [node_type for _ in range(num_nodes)]
    assert(len(node_type) == tables.nodes.num_rows)

    if ind_population is None:
        # set the individual populations based on what's in the nodes
        ind_population = [tskit.NULL for _ in range(num_individuals)]
        for j, u in enumerate(node_ind):
            if u >= 0:
                ind_population[u] = tables.nodes.population[j]
    assert(len(ind_population) == num_individuals)

    # check for consistency: every individual has two nodes, and populations agree
    ploidy = [0 for _ in range(num_individuals)]
    for j in samples:
        u = node_ind[j]
        assert(u >= 0)
        ploidy[u] += 1
        if tables.nodes.population[j] != ind_population[u]:
            raise ValueError("Inconsistent populations: nodes and individuals do not agree.")

    if any([p != 2 for p in ploidy]):
        raise ValueError("Not all individuals have two assigned nodes.")

    tables.nodes.set_columns(flags=tables.nodes.flags, time=tables.nodes.time,
                             population=tables.nodes.population, individual=node_ind,
                             metadata=tables.nodes.metadata,
                             metadata_offset=tables.nodes.metadata_offset)

    loc_vec, loc_off = tskit.pack_bytes(location)
    tables.individuals.set_columns(
            flags=ind_flags, location=loc_vec, location_offset=loc_off)

    individual_metadata = [IndividualMetadata(*x) for x in
                           zip(ind_id, age, ind_population, ind_sex, slim_ind_flags)]
    node_metadata = [None for _ in range(num_nodes)]
    for j in samples:
        node_metadata[j] = NodeMetadata(slim_id=node_id[j], is_null=node_is_null[j],
                                        genome_type=node_type[j])

    annotate_individual_metadata(tables, individual_metadata)
    annotate_node_metadata(tables, node_metadata)


def _set_populations(
        tables, pop_id=None, selfing_fraction=0.0, female_cloning_fraction=0.0,
        male_cloning_fraction=0.0, sex_ratio=0.5, bounds_x0=0.0, bounds_x1=0.0,
        bounds_y0=0.0, bounds_y1=0.0, bounds_z0=0.0, bounds_z1=0.0,
        migration_records=None):
    '''
    Adds to a TableCollection the information about populations required for SLiM
    to load a tree sequence. This will replace anything already in the Population
    table.
    '''
    num_pops = max(tables.nodes.population) + 1
    for md in tskit.unpack_bytes(tables.individuals.metadata,
                                   tables.individuals.metadata_offset):
        try:
            ind_md = decode_individual(md)
        except:
            raise ValueError("Individuals do not have metadata: "
                    "need to run set_nodes_individuals() first?")
        assert(ind_md.population < num_pops)
    if pop_id is None:
        pop_id = list(range(num_pops))
    assert(len(pop_id) == num_pops)

    if type(selfing_fraction) is float:
        selfing_fraction = [selfing_fraction for _ in range(num_pops)]
    assert(len(selfing_fraction) == num_pops)

    if type(female_cloning_fraction) is float:
        female_cloning_fraction = [female_cloning_fraction for _ in range(num_pops)]
    assert(len(female_cloning_fraction) == num_pops)

    if type(male_cloning_fraction) is float:
        male_cloning_fraction = [male_cloning_fraction for _ in range(num_pops)]
    assert(len(male_cloning_fraction) == num_pops)

    if type(sex_ratio) is float:
        sex_ratio = [sex_ratio for _ in range(num_pops)]
    assert(len(sex_ratio) == num_pops)

    if type(bounds_x0) is float:
        bounds_x0 = [bounds_x0 for _ in range(num_pops)]
    assert(len(bounds_x0) == num_pops)

    if type(bounds_x1) is float:
        bounds_x1 = [bounds_x1 for _ in range(num_pops)]
    assert(len(bounds_x1) == num_pops)

    if type(bounds_y0) is float:
        bounds_y0 = [bounds_y0 for _ in range(num_pops)]
    assert(len(bounds_y0) == num_pops)

    if type(bounds_y1) is float:
        bounds_y1 = [bounds_y1 for _ in range(num_pops)]
    assert(len(bounds_y1) == num_pops)

    if type(bounds_z0) is float:
        bounds_z0 = [bounds_z0 for _ in range(num_pops)]
    assert(len(bounds_z0) == num_pops)

    if type(bounds_z1) is float:
        bounds_z1 = [bounds_z1 for _ in range(num_pops)]
    assert(len(bounds_z1) == num_pops)

    if migration_records is None:
        migration_records = [[] for _ in range(num_pops)]
    assert(len(migration_records) == num_pops)
    for mrl in migration_records:
        for mr in mrl:
            assert(type(mr) is PopulationMigrationMetadata)

    population_metadata = [PopulationMetadata(*x) for x in
                           zip(pop_id, selfing_fraction, female_cloning_fraction,
                               male_cloning_fraction, sex_ratio, bounds_x0,
                               bounds_x1, bounds_y0, bounds_y1, bounds_z0, bounds_z1,
                               migration_records)]
    annotate_population_metadata(tables, population_metadata)


def _set_sites_mutations(
        tables, mutation_id=None, mutation_type=1, selection_coeff=0.0,
        population=tskit.NULL, slim_time=None):
    '''
    Adds to a TableCollection the information relevant to mutations required
    for SLiM to load in a tree sequence. This means adding to the metadata column
    of the Mutation table,  It will also
    - give SLiM IDs to each mutation
    - round Site positions to integer values
    - stack any mutations that end up at the same position as a result
    - replace ancestral states with ""
    This will replace any information already in the metadata or derived state
    columns of the Mutation table.
    '''
    num_mutations = tables.mutations.num_rows

    if mutation_id is None:
        mutation_id = list(range(num_mutations))
    assert(len(mutation_id) == num_mutations)

    if type(mutation_type) is int:
        mutation_type = [mutation_type for _ in range(num_mutations)]
    assert(len(mutation_type) == num_mutations)

    if type(selection_coeff) is float:
        selection_coeff = [selection_coeff for _ in range(num_mutations)]
    assert(len(selection_coeff) == num_mutations)

    if type(population) is int:
        population = [population for _ in range(num_mutations)]
    assert(len(population) == num_mutations)

    if slim_time is None:
        ## This may *not* make sense because we have to round:
        # slim_time = [(-1) * int(tables.nodes.time[u]) for u in tables.mutations.node]
        slim_time = [0 for _ in range(num_mutations)]
    assert(len(slim_time) == num_mutations)

    mutation_metadata = [[MutationMetadata(*x)] for x in
                         zip(mutation_type, selection_coeff, population, slim_time)]
    annotate_mutation_metadata(tables, mutation_metadata)

############
# Provenance
############
# See provenances.py for the structure of a Provenance entry.


def _set_provenance(tables, model_type, slim_generation):
    '''
    Appends to the provenance table of a :class:`TableCollection` a record containing
    the information that SLiM expects to find there.

    :param TableCollection tables: The table collection.
    :param string model_type: The model type: either "WF" or "nonWF".
    :param int slim_generation: The "current" generation in the SLiM simulation.
    '''
    pyslim_dict = make_pyslim_provenance_dict()
    slim_dict = make_slim_provenance_dict(model_type, slim_generation)
    tables.provenances.add_row(json.dumps(pyslim_dict))
    tables.provenances.add_row(json.dumps(slim_dict))


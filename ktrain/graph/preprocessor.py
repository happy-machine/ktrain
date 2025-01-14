from ..imports import *
from .. import utils as U
from ..preprocessor import Preprocessor
from .node_generator import NodeSequenceWrapper

from . import stellargraph as sg
from .stellargraph.mapper import GraphSAGENodeGenerator, GraphSAGELinkGenerator
from .stellargraph.layer import GraphSAGE



class NodePreprocessor(Preprocessor):
    """
    Text preprocessing base class
    """

    def __init__(self, G_nx, df, sample_size=10, missing_label_value=None):

        self.sampsize = sample_size       # neighbor sample size
        self.df = df                      # node attributes and targets
        # TODO: eliminate storage redundancy
        self.G = G_nx                     # networkx graph
        self.G_sg = None                  # StellarGraph 

        # clean df
        df.index = df.index.map(str)
        df= df[df.index.isin(list(self.G.nodes()))]

        # class names
        self.c = list(set([c[0] for c in df[['target']].values]))
        if missing_label_value is not None: self.c.remove(missing_label_value)
        self.c.sort()

        # feature names + target
        self.colnames = list(df.columns.values)
        if self.colnames[-1] != 'target':
            raise ValueError('last column of df must be "target"')

        # set by preprocess_train
        self.y_encoding = None


    def get_preprocessor(self):
        return (self.G, self.df)


    def get_classes(self):
        return self.c

    @property
    def feature_names(self):
        return self.colnames[:-1]


    def preprocess(self, df, G):
        return self.preprocess_test(df, G)


    def ids_exist(self, node_ids):
        """
        check validity of node IDs
        """
        df = self.df[self.df.index.isin(node_ids)]
        return df.shape[0] > 0



    def preprocess_train(self, node_ids):
        """
        preprocess training set
        """
        if not self.ids_exist(node_ids): raise ValueError('node_ids must exist in self.df')

        # subset df for training nodes
        df_tr = self.df[self.df.index.isin(node_ids)]

        # one-hot-encode target
        self.y_encoding = sklearn.feature_extraction.DictVectorizer(sparse=False)
        train_targets = self.y_encoding.fit_transform(df_tr[["target"]].to_dict('records'))


        # return generator
        G_sg = sg.StellarGraph(self.G, node_features=self.df[self.feature_names])
        self.G_sg = G_sg
        generator = GraphSAGENodeGenerator(G_sg, U.DEFAULT_BS, [self.sampsize, self.sampsize])
        train_gen = generator.flow(df_tr.index, train_targets, shuffle=True)
        return NodeSequenceWrapper(train_gen)


    def preprocess_valid(self, node_ids):
        """
        preprocess validation nodes (transductive inference)
        node_ids (list):  list of node IDs that generator will yield
        """
        if not self.ids_exist(node_ids): raise ValueError('node_ids must exist in self.df')
        if self.y_encoding is None:
            raise Exception('Unset parameters. Are you sure you called preprocess_train first?')

        # subset df for validation nodes
        df_val = self.df[self.df.index.isin(node_ids)]


        # one-hot-encode target
        val_targets = self.y_encoding.transform(df_val[["target"]].to_dict('records'))

        # return generator
        if self.G_sg is None:
            self.G_sg = sg.StellarGraph(self.G, node_features=self.df[self.feature_names])
        generator = GraphSAGENodeGenerator(self.G_sg, U.DEFAULT_BS, [self.sampsize,self.sampsize])
        val_gen = generator.flow(df_val.index, val_targets, shuffle=False)
        return NodeSequenceWrapper(val_gen)



    def preprocess_test(self, df_te, G_te):
        """
        preprocess for inductive inference
        df_te (DataFrame): pandas dataframe containing new node attributes
        G_te (Graph):  a networkx Graph containing new nodes
        """
        if self.y_encoding is None:
            raise Exception('Unset parameters. Are you sure you called preprocess_train first?')

        # get aggregrated df
        #df_agg = pd.concat([df_te, self.df]).drop_duplicates(keep='last')
        df_agg = pd.concat([df_te, self.df])
        #df_te = pd.concat([self.df, df_agg]).drop_duplicates(keep=False)


        # get aggregrated graph
        is_subset = set(self.G.nodes()) <= set(G_te.nodes())
        if not is_subset:
            raise ValueError('Nodes in self.G must be subset of G_te')
        G_agg = nx.compose(self.G, G_te)    

        
        # one-hot-encode target
        if 'target' in df_te.columns:
            test_targets = self.y_encoding.transform(df_te[["target"]].to_dict('records'))
        else:
            test_targets = [-1] * len(df_te.shape[0])

        # return generator
        G_sg = sg.StellarGraph(G_agg, node_features=df_agg[self.feature_names])
        generator = GraphSAGENodeGenerator(G_sg, U.DEFAULT_BS, [self.sampsize,self.sampsize])
        test_gen = generator.flow(df_te.index, test_targets, shuffle=False)
        return NodeSequenceWrapper(test_gen)





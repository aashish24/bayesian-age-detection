"""
Code to predict the age of Twitter users based solely on who they follow (friends)
Trains a model using A set of Twitter users with known ages and their friends
Trainining outputs a predictive model that consumes an edge list of Twitter IDs and returns a class
"""

__author__ = 'benchamberlain'

import numpy as np
import pandas as pd
import utils
import itertools
from sklearn.model_selection import StratifiedKFold
import argparse


class AgeDetector:
    def __init__(self, n_classes=7):
        print 'initialising age detector'
        self.n_classes = n_classes
        self.PRIOR = [1.0 / self.n_classes] * self.n_classes  # assume uniformative prior for the data sample
        self.model = None

    def _add_prior_knowledge(self, pos_counts, bucket_counts, n_data):
        """
        Adds the a and b parameters that compose the equation
        P(star=1|age) = (a+m)/(a+b+n+l)
        where a and b are beta hyperparameters set to 1 and n_twitter_users / n_followers
        set because E(mu) = a / (a+b) for the beta distribution
        Here, we are using anonamised data and so n_twitter_users is the number of training points and n_followers is
        the number of labelled users following each feature account
        :param pos_counts: array size [nInfluencers, nCategories] of follower counts
        :param bucket_counts: A pandas DataFrame of shape [nCategories, 1] of the total number of observations in each age category
        :param n_data: the number of training examples
        """
        # add a to the numerator
        # pos_counts += 1  # this is m + a
        # add a + b to the denominator
        total_counts = np.tile(bucket_counts.values, (1, pos_counts.shape[1]))  # this is n
        b = total_counts / 10.0
        n_followers = pos_counts.sum(axis=0)
        a = b * n_followers / n_data
        pos_counts = pos_counts + a  # this is a + m
        total_counts = total_counts + a + 1  # this is n + l + b + a

        return pos_counts, total_counts

    def fit(self, X, y):
        """
        generate the model
        :param X: The features
        :param y: The labels
        :return: None
        """
        bins, counts = np.unique(y, return_counts=True)
        bucket_counts = pd.DataFrame(index=bins, data=counts)
        n_cats = len(bins)
        n_data, n_features = X.shape
        pos_counts = np.zeros(shape=(n_cats, n_features))
        # sum the columns by each age category
        for cat in bins:
            mask = y == cat
            sums = X[mask, :].sum(axis=0)
            pos_counts[cat - 1, :] = sums

        pos_counts, total_counts = self._add_prior_knowledge(pos_counts, bucket_counts, n_data)

        self.model = np.divide(pos_counts, total_counts)

    def predict(self, X):
        """
        Predict the values for each row of X
        :param X: the input values
        :return:
        """

        n_cats, _ = self.model.shape
        # create an array for storing the joint log probabilities
        joint = np.zeros(shape=(X.shape[0], n_cats))
        # This is the fastest way of iterating through nonzero elements of a sparse matrix
        # http://stackoverflow.com/questions/4319014/iterating-through-a-scipy-sparse-vector-or-matrix
        coo_mat = X.tocoo()
        for row, col in itertools.izip(coo_mat.row, coo_mat.col):
            joint[row, :] += self.model[:, col]

        joint += np.log(self.PRIOR)
        # need to unormalise before unlogging to prevent underflow
        # This is similar to the logsumexp trick
        joint -= np.max(joint, axis=1)[:, np.newaxis]
        # convert back to probability space
        probs = np.exp(joint)
        # normalise
        normaliser = np.sum(probs, axis=1)[:, np.newaxis]

        probs = np.divide(probs, normaliser)

        predicted_cat = probs.argmax(axis=1) + 1
        np.savetxt('age_preds.csv', predicted_cat, delimiter=',')

        return predicted_cat


def run_cv_pred(X, y, clf, n_folds):
    """
    Run n-fold cross validation returning a prediction for every row of X
    :param X: A scipy sparse feature matrix
    :param y: The target labels corresponding to rows of X
    :param clf: The
    :param n_folds:
    :return:
    """
    # Construct a kfolds object
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True)
    splits = skf.split(X, y)
    y_pred = y.copy()

    # Iterate through folds
    for idx, (train_index, test_index) in enumerate(splits):
        X_train, X_test = X[train_index], X[test_index]
        y_train = y[train_index]
        # Initialize a classifier with key word arguments
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        macro, micro = utils.get_metrics(preds, y[test_index])
        print 'run ', idx
        print 'macro: ', macro
        print 'micro: ', micro
        y_pred[test_index] = preds

    return y_pred


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run age detector on public 7 class dataset',
                                     epilog='Classes are 0: 10-19, 1: 20-29, 2: 30-39, 3: 40-49, 4: 50-59, 5: 60-69, 6: 70-79')
    parser.add_argument(
        'x_path', type=str,
        nargs='+', default='resources/features.p', help='the location of the features')
    parser.add_argument(
        'y_path', type=str,
        nargs='+', default='resources/labels.p', help='the location of the labels')
    parser.add_argument(
        '-nfolds', type=int,
        nargs='+', default=3, help='number of stratified folds to split the data into for cross-validation')
    args = parser.parse_args()

    x, y = utils.read_data(args.x_path[0], args.y_path[0], threshold=0)
    n_classes = len(np.unique(y))
    print('n_classes: {}'.format(n_classes))
    clf = AgeDetector(n_classes)
    n_folds = args.nfolds[0]
    y_pred = run_cv_pred(x, y, clf, n_folds)

import argparse

import sklearn.metrics as metrics
from sklearn import linear_model
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.externals import joblib
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from src.data_prep import DataPrep
from src.predict import Predictor
from src.setting import *

SEED = 1


class Trainer():
    def __init__(self, train, validation_ratio,
                 preprocess: DataPrep,
                 stratify=None, n_estimators=100):

        print('\t # estimators = {}'.format(n_estimators))
        self.n_estimator = n_estimators
        # limit to only interested features
        features = preprocess.features
        self.features = features
        cols = features + ['SalePrice']

        compact_train = train[cols]
        X = compact_train.drop('SalePrice', axis='columns')
        y = compact_train['SalePrice']

        # split into two parts: train and validation
        if not stratify:
            X_train, X_valid, y_train, y_valid = train_test_split(X, y, test_size=validation_ratio, random_state=SEED)
        else:
            X_train, X_valid, y_train, y_valid = train_test_split(X, y, test_size=validation_ratio, stratify=stratify,
                                                                  random_state=SEED)

        self.X_train, self.y_train = X_train, y_train
        self.X_valid, self.y_valid = X_valid, y_valid

        lin_models = set_linear_models()
        tree_models = set_tree_models(n_estimators)
        self.models = tree_models
        # self.models = {**lin_models, **tree_models}  # join two dicts
        self.predictions = dict()

    def benchmark(self, pred_file):

        errors = dict()
        for name, predictor in self.models.items():
            errors[name] = self.eval(predictor, name)

        error_df = pd.DataFrame({'model': list(errors.keys()), 'mean_squared_log_error': list(errors.values())})
        error_df['n_estimator'] = self.n_estimator

        predict_df = self.retrieve_predictions()
        predict_df.to_csv(pred_file, index=False)
        print('dumped predictions to file {}'.format(pred_file))

        return error_df

    def eval(self, model, name):

        model.fit(self.X_train, self.y_train)
        self.dump_predictor(model, name)

        y_pred = model.predict(self.X_valid)
        self.predictions[name] = y_pred

        try:
            error = metrics.mean_squared_log_error(self.y_valid, y_pred)
            return error
        except ValueError as e:
            return np.nan

    def dump_predictor(self, model, name):
        fname = '{}'.format(rm_space(name)) + str(self.n_estimator) + '.pkl'
        predictor_file = os.path.join(MODEL_DIR, fname)
        predictor = Predictor(model, self.features)
        joblib.dump(predictor, predictor_file)
        print('dumped trained predictor {} to file {}'.format(name, predictor_file))

    def retrieve_predictions(self):
        predict_df = self.X_valid
        predict_df['SalePrice'] = self.y_valid
        for model in self.models.keys():
            predict_df['price_predict_{}'.format(model)] = self.predictions[model]
            predict_df['{}_error'.format(rm_space(model))] = self.predictions[model] - predict_df['SalePrice']

        return predict_df


def set_linear_models():
    # lin_reg = linear_model.LinearRegression()
    ridge_reg = linear_model.Ridge(random_state=SEED)
    lasso_reg = linear_model.Lasso(random_state=SEED)
    lin_predictors = [lasso_reg, ridge_reg]  # lin_reg, ridge_reg
    lin_names = ['Lasso Regression', 'Ridge Regression']  # 'Linear Regression'
    return dict(zip(lin_names, lin_predictors))


def set_tree_models(n_estimators=100):
    gb_reg = GradientBoostingRegressor(random_state=SEED, n_estimators=n_estimators)
    rf_reg = RandomForestRegressor(random_state=SEED, n_estimators=n_estimators)
    xgb_reg = XGBRegressor(n_estimators=n_estimators)

    tree_predictors = [gb_reg, rf_reg, xgb_reg]
    tree_names = ['Boosted Regression Tree', 'Random Forest',
                  'XGBoost']

    return dict(zip(tree_names, tree_predictors))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_file',
                        help='name of input file, e.g. data_all.csv'
                        )
    parser.add_argument('--metrics_file',
                        help='name of file for saving metrics, e.g. metrics.csv'
                        )
    parser.add_argument('--pred_file',
                        help='name of file for saving predictions, e.g. predictions.csv')

    return parser.parse_args()


def rm_space(s):
    return s.replace(' ', '_').lower()


def load_data_prep(fname):
    return joblib.load(os.path.join(DAT_DIR, fname))


if __name__ == '__main__':
    # args = parse_args()
    # input_file = os.path.join(DAT_DIR, vars(args)['input_file'])
    # metrics_file = os.path.join(RES_DIR, vars(args)['metrics_file'])
    # pred_file = os.path.join(RES_DIR, vars(args)['pred_file'])

    input_file = os.path.join(DAT_DIR, 'data_all.csv')
    data_all = pd.read_csv(input_file)
    print('Loaded all data')

    dp = load_data_prep(fname='data_prep.pkl')
    train = data_all[data_all['SalePrice'].notnull()]
    print('# rows in train data: {}'.format(train.shape[0]))

    print('Train tree-based models')
    error_df = pd.DataFrame()
    for n_estimators in np.arange(100, 550, step=50):   # 150, 200 helps
        trainer = Trainer(train,
                          validation_ratio=0.1,
                          preprocess=dp,
                          n_estimators=n_estimators)

        pred_file = os.path.join(RES_DIR, '{}_est_validation.csv'.format(n_estimators))
        error_df = pd.concat([error_df, trainer.benchmark(pred_file)])

    metrics_file = os.path.join(RES_DIR, 'metrics.csv')
    error_df.to_csv(metrics_file, index=False)
    print('dumped errors to file {}'.format(metrics_file))

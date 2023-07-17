from math import *

import numpy as np
from scipy.integrate import solve_ivp
import matplotlib.pyplot as plt
from PIL import Image as im

from model import model

def create_model(name, f, t_span, initial_conditions, **kwargs):
    """Creates a model object
    Parameters
    ----------
    name : str
        Name of the model.
    f : function
        Function defining the system of ODEs.
    t_span : 2-tuple
        Tuple containing the start and end time of the simulation.
    initial_conditions : array_like
        Array containing the initial conditions of the system. The length 
        of the array must be equal to the number of unknowns.
    **kwargs : dict
        Dictionary containing the optional arguments of the model. The
        possible arguments are:
            t_eval : int, optional
                Number of time points to evaluate the solution at. The default is 1000.
            p : array_like, optional
                Array containing the parameters of the system. The default is None.
            description : str, optional
                Description of the model. (i.e. what represent each parameter, what
                process is described by the model, etc.) The default is None.
    Returns
    -------
    model
        Model object.
    """

    if 'p' in kwargs and kwargs['p'] is not None:
        if isinstance(kwargs['p'], list):
            p = kwargs['p']
            # eval every callable object in the list
            p = [float(p[i]()) if callable(p[i]) else p[i] for i in range(len(p))]
        else:
            p = []
            for i in kwargs['p'].split(','):
                try:
                    p.append(float(i))
                except ValueError:
                    p.append(float(eval(i)))
    else:
        p = None
    
    if isinstance(initial_conditions, list):
        ic = initial_conditions
    else:
        ic = [float(i) for i in initial_conditions.split(',')]
    
    if isinstance(t_span, list):
        ts = t_span
    else:
        ts = [float(i) for i in t_span.split(',')]

    te = int(kwargs['t_eval']) if ('t_eval' in kwargs and kwargs['t_eval'] is not None) else 1000
    desc = kwargs['description'] if 'description' in kwargs else None

    functions = []
    for func in [i for i in f.split(',')]:
        if '=' in func:
            functions.append(func.split('=')[1])
        else:
            functions.append(func)


    if len(functions) != len(ic):
        raise ValueError('The number of initial conditions must be equal to the number of unknowns.')

    def f(t, y, *p):
        dydt = []
        for i in range(len(functions)):
            dydt.append(eval(functions[i]))
        return dydt

    return model(name, f, ts, ic, te, p, desc)

def solve_model(model):
    """Solves a model
    Parameters
    ----------
    model : model
        Model to solve.
    Returns
    -------
    array_like
        Array containing the solution of the model.
    """
    sol = solve_ivp(model.f, model.t_span, model.initial_conditions, t_eval=np.linspace(model.t_span[0], model.t_span[1], model.t_eval), args=model.p)
    return sol

def plot_model(model_name, sol, show=True, save=False):
    """Plots the solution of a model
    Parameters
    ----------
    mode_name : str
        Name of the model.
    sol : array_like
        Solution of the model to plot.
    show : bool, optional
        Whether to show the plot or not. The default is True.
    save : bool, optional
        Whether to save the plot or not. The default is False.
    path : str, optional
        Path to the file to save the plot to. The default is None.
    """
    i = 0
    for curve in sol.y:
        plt.plot(sol.t, curve, label = 'y' + str(i) + '(t)')
        i += 1
    plt.xlabel('t')
    plt.ylabel('yi(t)')
    plt.legend(loc='best')
    if model_name is not None:
        plt.title(model_name)
    if save:
        path = model_name + '.png'
        plt.savefig(path)
        plt.close()
    if show:
        plt.show()

    if len(sol.y) == 3:
        ax = plt.axes(projection='3d')
        ax.plot3D(sol.y[0], sol.y[1], sol.y[2])
        ax.set_xlabel('y0(t)')
        ax.set_ylabel('y1(t)')
        ax.set_zlabel('y2(t)')
        ax.set_title(model_name)
        if save:
            path = model_name + '3d.png'
            plt.savefig(path)
            plt.close()
        if show:
            plt.show()


# love model
love_func = """dJdt = (p[1] + p[4] - p[8] - p[12]) *  y[0] + (p[2] - p[6] - p[10]) * y[1], 
dRdt = (p[3] - p[7] - p[11]) * y[0] + (p[0] + p[5] - p[9] - p[13]) * y[1]"""

ideal = create_model('ideal', love_func, '0, 1', '5, 17', t_eval=1000, p='0.9,0.9,0.9,0.9,0.8,0.8,0.1,0.1,0.1,0.1,0.1,0.1,0.1,0.1')
asymmetric = create_model('asymmetric', love_func, '0, 5', '3, 8', t_eval=1000, p='0.9,0.3,0.3,0.8,0.3,0.8,0.8,0.9,0.8,0.8,0.3,0.8,0.2,0.8')
spiral = create_model('spiral', love_func, '0, 15', '10, 2', t_eval=1000, p='0.126,0.98,0.98,0.126,0.126,0.64,0.5,0.5,0.5,0.5,0.1,0.64,0.95,0.95')

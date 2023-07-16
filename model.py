class model:
    """Defines a system of Ordinary Differential Equations, initial conditions 
    and a time span for the simulation."""
    def __init__(self, name, f, t_span, initial_conditions, t_eval=10000, p=None, description=None):
        """Initializes the model class
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
        t_eval : int, optional
            Number of time points to evaluate the solution at. The default is 1000.
        p : array_like, optional
            Array containing the parameters of the system. The default is None.
        description : str, optional
            Description of the model. (i.e. what represent each parameter, what
            process is described by the model, etc.) The default is None.
        """
        self.name = name
        self.f = f
        if t_span[0] >= t_span[1]:
            raise ValueError('The start time must be smaller than the end time.')
        if len(t_span) != 2:
            raise ValueError('The time span must be a 2-tuple.')
        self.t_span = t_span

        self.initial_conditions = initial_conditions
        self.t_eval = t_eval
        self.p = p
        self.description = description

import logging
import traceback
from collections import deque
import ast
import math

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from model import model
from solver import create_model, solve_model, plot_model, ideal, asymmetric, spiral, love_func
from config import TOKEN


# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# ------------------------- CONVERSATION STATES ----------------------------#
SCENARIO, SOLVE_OR_EDIT_TUTORIAL, INPUT_IC_TUTORIAL = range(3)
VARIABLES, EQUATION, TS_IC, PARAMETERS, SOLVE_OR_EDIT, EDIT, EDITED = range(7)

# ------------------------------ KEYBOARDS ---------------------------------#
keyboards = {
    "main" : [["/create", "/tutorial"]],
    "rj": [["Relación ideal", "Relación asimétrica"], ["Relación espiral", "/cancel"]],
    "solve_or_edit": [["solve", "edit"], ['/cancel']],
    "edit": [["edit", "/cancel"]],
    "edit_options": [["parameters", "initial conditions"], ["time interval", "number of points"], ["/cancel"]],
    "tutorial": [["Radioactive decay", "Romeo and Juliet"], ["/cancel"]],
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Hello! I'm a bot that helps you to create and solve systems of differential"
        "equations and get the results in a nice plot. Press create to submit a" 
        "new model or go to the tutorial to learn how to use me.",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["main"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """cancels any active conversation and returns to the start state cancel is 
    a fallback state, canceling while editing a model will discard the model 
    and return to the start state"""
    logger.info("User %s canceled the conversation.", update.message.from_user.first_name)

    # clear user data
    context.user_data.clear()

    await update.message.reply_text(
        "What do you want to do now?",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["main"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message"""
    # Log the error
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    error = tb_list[-1]

    msg = "Ups, something went wrong. Please try again or contact the developer if the problem persists.\n" + error 

    # Finally, send the message
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=msg, parse_mode=ParseMode.HTML, 
        reply_markup=ReplyKeyboardMarkup([["/cancel"]], one_time_keyboard=True, resize_keyboard=True)
    )


# -------------------------- CREATE CONVERSATION -------------------------- #

async def create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the create conversation. Starts by asking the user for
    the variables of the EDOs"""

    await update.message.reply_text(
        "Enter the variables separated by a comma\n"
        "You can also /cancel the creation of the model at any time. Doing this will discard "
        "any changes so be careful.",
        reply_markup=ReplyKeyboardRemove()
    )

    return VARIABLES

async def create_variables(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """State of the create conversation.
    Stores the variables previously submitted by the user in a queue in the user_data dictionary.
    Then asks the user for the right hand side of the equation of the derivative of the current variable."""

    #logs
    logger.info("User %s submitted variables: %s", update.message.from_user.first_name, update.message.text)

    # store variables in a queue in the user_data dictionary
    if 'variables' not in context.user_data:
        # remove spaces
        v = update.message.text.replace(" ", "")
        context.user_data['variables'] = deque(v.upper().split(','))
        context.user_data['variables_ic'] = deque(v.upper().split(',')) # this is a copy of the variables queue that will be used to ask for the initial conditions
        context.user_data['variables_list'] = v.lower().split(',')
        current = context.user_data['variables'].popleft()

    msg = f"Enter the right hand side of the equation involving the derivative of {current}\n"
    msg += f"<code>d{current}/dt = ...</code>."

    if 'tutorial' in context.user_data:
        if context.user_data['tutorial'] == 'rd':
            msg = context.user_data['msgs'][1] + msg

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML
    )

    return EQUATION

async def create_equation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Stores the equation previously submitted by the user in a list in the user_data dictionary.
    If there are more variables to process, goes back to the VARIABLES state. Otherwise, 
    asks the user for the time interval.
    """

    #logs
    logger.info("User %s submitted equation: %s", update.message.from_user.first_name, update.message.text)

    # store equation in a list in the user_data dictionary
    if 'equations' not in context.user_data: # first time in this state
        context.user_data['equations'] = [update.message.text.lower()]
    else:
        context.user_data['equations'].append(update.message.text.lower())
    
    if len(context.user_data['variables']) > 0: # there are more variables to process
        current = context.user_data['variables'].popleft()
        await update.message.reply_text(
            f"Enter the right hand side of the equation involving the derivative of {current}\n"
            f"<code>d{current}/dt = ...</code>.",
            parse_mode=ParseMode.HTML,
        )
        return EQUATION
    else: # no more variables to process, ask for time interval
        # format the equations in a string for use in the solver
        f = ','.join(context.user_data['equations'])
        v_list = context.user_data['variables_list']
        # Replace all coincidences of the strings in v_list with the string f with 
        # "y[i]" where i is the index of the string in v_list
        for i, v in enumerate(v_list):
            f = f.replace(v.lower(), f"y[{i}]")
        
        # store the formatted equations in the user_data dictionary
        context.user_data['f'] = f

        msg = "Enter the time interval separated by a comma\n"
        msg += "i.e. <code>0, 10</code>."
        if 'tutorial' in context.user_data:
            if context.user_data['tutorial'] == 'rd':
                msg = context.user_data['msgs'][2] + msg

        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
        )
        return TS_IC

async def create_time_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Stores the time interval previously submitted by the user in the user_data dictionary.
    Then keeps asking the user for the initial conditions of the variables until there are no more variables.
    """

    if 'ts' not in context.user_data: # first time in this state
        #logs
        logger.info("User %s submitted time interval: %s", update.message.from_user.first_name, update.message.text)

        # store time interval in the user_data dictionary
        context.user_data['ts'] = update.message.text

        # ask for initial conditions
        current = context.user_data['variables_ic'].popleft()

        msg = f"Enter the initial condition for {current}\n"
        msg += f"<code>{current}(0) = ...</code>."
        if 'tutorial' in context.user_data:
            if context.user_data['tutorial'] == 'rd':
                msg = context.user_data['msgs'][3] + msg
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
        )

        return TS_IC
    else:
        # asks for the next initial condition if there are more variables.
        # otherwise, asks the user for the value of the parameters if any.
        #logs
        logger.info("User %s submitted initial condition: %s", update.message.from_user.first_name, update.message.text)

        # store initial condition in the user_data dictionary
        if 'ic' not in context.user_data:
            context.user_data['ic'] = update.message.text
        else:
            context.user_data['ic'] += ',' + update.message.text

        if len(context.user_data['variables_ic']) > 0: # there are more variables to process
            current = context.user_data['variables_ic'].popleft()
            await update.message.reply_text(
                f"Enter the initial condition for {current}\n"
                f"<code>{current}(0) = ...</code>.",
                parse_mode=ParseMode.HTML,
            )

            return TS_IC
        else: 
            f = context.user_data['f']
            # store number of points in the user_data dictionary
            context.user_data['te'] = 1000 # default value, can be changed by the user

            # automatically detect parameters in f
            # first get all names using python ast
            p = [
                node.id for node in ast.walk(ast.parse(f)) 
                if isinstance(node, ast.Name)
            ]
            # then remove duplicates
            p = list(set(p))
            # then remove 'y'
            p.remove('y')
            # then remove math functions
            p = [x for x in p if x not in dir(math)]
            # get all function calls using python ast
            f_calls = [node.func.id for node in ast.walk(ast.parse(f)) if isinstance(node, ast.Call)]
            print('function calls: ', f_calls)
            # then remove function calls from p
            p = [x for x in p if x not in f_calls]
            print('parameters', p)
            # store parameters in a queue in the user_data dictionary
            context.user_data['p_names'] = deque(p)
            context.user_data['p_list'] = p

            # replace all coincidences of the strings in p with the string f with
            # "p[i]" where i is the index of the string in p
            for i, v in enumerate(p):
                context.user_data['f'] = context.user_data['f'].replace(v.lower(), f"p[{i}]")
            
            # ask for parameters
            if len(p) > 0:
                current = context.user_data['p_names'].popleft()

                msg = f"Enter the value of {current}\n"
                msg += f"<code>{current} = ...</code>."
                if 'tutorial' in context.user_data:
                    if context.user_data['tutorial'] == 'rd':
                        msg = context.user_data['msgs'][5] + msg
                await update.message.reply_text(
                    msg,
                    parse_mode=ParseMode.HTML,
                )
                return PARAMETERS
            else:
                # no parameters to process
                # create model
                params = context.user_data['params'] if 'params' in context.user_data else None
                f = context.user_data['f']
                ic = context.user_data['ic']
                ts = context.user_data['ts']
                te = context.user_data['te']
                # print
                print('f', f)
                print('ic', ic)
                print('ts', ts)
                print('te', te)
                print('params', params)
                #
                m = create_model("model", f, ts, ic, t_eval=te, p=params)
                #store model
                context.user_data['model'] = m

                msg = "Model created. Do you want to solve and plot the model or edit it first?"
                if 'tutorial' in context.user_data:
                    if context.user_data['tutorial'] == 'rd':
                        msg = context.user_data['msgs'][6] + msg
                await update.message.reply_text(
                    msg,
                    reply_markup=ReplyKeyboardMarkup(
                        keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
                    ),
                )
                return SOLVE_OR_EDIT

async def create_parameters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Stores the parameters previously submitted by the user in the user_data dictionary.
    Then keeps asking the user for the parameters until there are no more parameters.
    """

    #logs
    logger.info("User %s submitted parameter: %s", update.message.from_user.first_name, update.message.text)

    # store parameter in the user_data dictionary
    if 'params' not in context.user_data:
        context.user_data['params'] = update.message.text
    else:
        context.user_data['params'] += ',' + update.message.text

    if len(context.user_data['p_names']) > 0: # there are more parameters to process
        current = context.user_data['p_names'].popleft()
        await update.message.reply_text(
            f"Enter the value of {current}\n"
            f"<code>{current} = ...</code>.",
            parse_mode=ParseMode.HTML,
        )

        return PARAMETERS
    else: 
        # no parameters to process
        # create model
        params = context.user_data['params']
        f = context.user_data['f']
        ic = context.user_data['ic']
        ts = context.user_data['ts']
        te = context.user_data['te']
        # print
        print('f', f)
        print('ic', ic)
        print('ts', ts)
        print('te', te)
        print('params', params)
        #
        m = create_model("model", f, ts, ic, t_eval=te, p=params)
        #store model
        context.user_data['model'] = m

        await update.message.reply_text(
            "Model created. Do you want to solve and plot the model or edit it first?",
            reply_markup=ReplyKeyboardMarkup(
                keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return SOLVE_OR_EDIT

async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Solves and plots the model previously created by the user.
    """
    #logs
    logger.info("User %s solved the model", update.message.from_user.first_name)

    # solve model
    sol = solve_model(context.user_data['model'])

    # plot model
    plot_model("model", sol, show=False, save=True)

    reply_markup=ReplyKeyboardMarkup(
            keyboards["edit"], one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="edit or cancel"
    )

    await update.message.reply_photo("model.png", reply_markup=reply_markup)
    if len(sol.y) == 3:
        await update.message.reply_photo("model3d.png", reply_markup=reply_markup)
    
    return SOLVE_OR_EDIT

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Asks the user what to edit.
    """
    #logs
    logger.info("User %s wants to edit the model", update.message.from_user.first_name)

    await update.message.reply_text(
        "What do you want to edit?",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["edit_options"], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return EDIT

async def input_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Asks for the new values of the selected option.
    """
    # logs
    logger.info("User %s wants to edit %s", update.message.from_user.first_name, update.message.text)
    
    context.user_data['edit'] = update.message.text

    if update.message.text == "initial conditions" or update.message.text == "time interval":
        msg = f"Enter the new {update.message.text} separated by a comma."
    elif update.message.text == "number of points":
        msg = "Enter the number of points to plot"
    else:
        if 'params' in context.user_data:
            p = ""
            for i in context.user_data['p_list']:
                p += i + ", "
            msg = "Enter the value of the parameters separeted by a comma.\n\n" + p
        else:
            await update.message.reply_text(
                "There are no parameters to edit.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
                ),
            )
            return SOLVE_OR_EDIT
    
    await update.message.reply_text(
        msg
    )
    return EDITED

async def edit_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ State of the create conversation.
    Remakes the model with the new values.
    """
    # logs
    logger.info("User %s edited the model", update.message.from_user.first_name)
    
    if context.user_data['edit'] == "initial conditions":
        context.user_data['ic'] = update.message.text
    elif context.user_data['edit'] == "time interval":
        context.user_data['ts'] = update.message.text
    elif context.user_data['edit'] == "number of points":
        context.user_data['te'] = update.message.text
    else:
        context.user_data['params'] = update.message.text
    
    # create model
    params = context.user_data['params'] if 'params' in context.user_data else None
    f = context.user_data['f']
    ic = context.user_data['ic']
    ts = context.user_data['ts']
    te = context.user_data['te']
    # print
    print('f', f)
    print('ic', ic)
    print('ts', ts)
    print('te', te)
    print('params', params)
    #

    m = create_model("model", f, ts, ic, t_eval=te, p=params)

    #store model
    context.user_data['model'] = m

    await update.message.reply_text(
        "Model created. Do you want to solve and plot the model or edit it first?",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SOLVE_OR_EDIT


# ---------------------------- TUTORIAL ---------------------------- #

async def tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Shows the available examples and asks the user to choose one"""
    # Logs
    logger.info("User %s started the tutorial.", update.message.from_user.first_name)

    await update.message.reply_text(
        "Here you will get a grasp of the bot's capabilities through following "
        "the steps of a few examples. Choose one to see it in action. "
        "Romeo and Juliet is a fun example but not recommended for newcommers.",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["tutorial"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

async def tutorial_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Readies the chosen example. 
    Works as an entry point for the create conversation."""
    # Logs
    logger.info("User %s chose %s", update.message.from_user.first_name, update.message.text)

    if update.message.text == "Radioactive decay":
        context.user_data['tutorial'] = 'rd'
        context.user_data['msgs'] = rd_tutorial_msgs()
        await update.message.reply_text(context.user_data['msgs'][0], parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    
    return VARIABLES


# ------------------------ ROMEO AND JULIET ------------------------ #
async def rj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Presents love model to the user"""
    msg = (
        "En este tutorial se introducirá al usuario en el uso de las funciones "
        "del bot mediante un sistema de dos ecuaciones diferenciales que representa "
        "el amor entre dos personas. Existen varios escenarios donde el usuario "
        "podrá modificar los valores iniciales y observar commo evoluciona la "
        "relación. El modelo es el siguiente:\n\n"
        "<code>dJ/dt = [aR + mJ - kJ - bJ] * J(t) + [cJ - tJ - uJ] * R(t)</code>\n"
        "<code>dR/dt = [cR - tR - uR] * J(t) + [aJ + mR - kR - bR] * R(t)</code>\n\n"
        "Donde:\n"
        "<code>R(t)</code> y <code>J(t)</code> son dos variables en función del tiempo que representan el "
        "amor de R (Romeo) y J (Julietta) respectivamente.\n"
        "<code>aR, aJ, cJ, cR, mJ, mR, tJ, tR, kJ, kR, uJ, uR, bJ, bR</code> son "
        "parámetros que representan las diferentes fuerzas que actúan sobre el "
        "sistema. Todos los parámetros son positivos y van de 0 a 1.\n"
        "<code>aJ</code>: sentimiento de Romeo hacia Julietta\n"
        "<code>aR</code>: sentimiento de Julietta hacia Romeo\n"
        "<code>cJ</code>: grado de respuesta de Julietta hacia los sentimientos de Romeo\n"
        "<code>cR</code>: grado de respuesta de Romeo hacia los sentimientos de Julietta\n"
        "<code>mJ</code>: capacidad de ahorrar dinero de Julietta\n"
        "<code>mR</code>: capacidad de ahorrar dinero de Romeo\n"
        "<code>tJ</code>: tolerancia de Julietta al gasto de dinero de Romeo\n"
        "<code>tR</code>: tolerancia de Romeo al gasto de dinero de Julietta\n"
        "<code>kJ</code>: tiempo invertido por Julietta en redes sociales\n"
        "<code>kR</code>: tiempo invertido por Romeo en redes sociales\n"
        "<code>uJ</code>: celos de Julietta\n"
        "<code>uR</code>: celos de Romeo\n"
        "<code>bJ</code>: inestabilidad emocional de Julietta\n"
        "<code>bR</code>: inestabilidad emocional de Romeo\n\n"
        "Para comenzar, elige el escenario que deseas simular."
    )
    #log
    logger.info("User %s started the tutorial", update.message.from_user.first_name)

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboards["rj"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SCENARIO

async def scenario_ideal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Presents the ideal model"""
    #log
    logger.info("User %s chose the ideal scenario", update.message.from_user.first_name)

    msg = (
        "Romeo y Julieta están perdidamente enamorados entre sí, por lo que el "
        "valor de <code>aR, aJ, cR y cJ es 0.9</code>. No les importa que su pareja gaste dinero "
        "(<code>mJ y mR son 0.8</code>). Pasan mucho tiempo juntos, no son celosos, etc. El "
        "valor de los parámetros restantes es 0.1"
    )

    #store model
    context.user_data['model'] = ideal
    
    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SOLVE_OR_EDIT_TUTORIAL

async def scenario_asymmetric(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """presents the asymmetric model"""
    #log
    logger.info("User %s chose the asymmetric scenario", update.message.from_user.first_name)

    msg = (
        "Este tipo de relación estará caracterizado por un Romeo enamorado de "
        "Julietta, pero esta no le responde con el mismo cariño, por lo que <code>aR = 0.3, "
        "aJ = 0.9, cR = 0.8, cJ = 0.3</code>. A diferencia de Julietta, Romeo siempre "
        "se encuentra celoso (<code>uR = 0.8, uJ = 0.3</code>). Ellos no les importa malgastar "
        "el dinero porque ella no cree tener un futuro con él, mientras que Romeo "
        "desea complacerla en todo momento (<code>tR = 0.9, tJ = 0.8, mR = 0.8, mJ = 0.3</code>). "
        "Ambos pasan mucho tiempo en redes sociales (<code>kR = 0.8, kJ = 0.8</code>). Toda esta "
        "situación conlleva a un Romeo inestable emocionalmente (<code>bR = 0.8</code>), algo que "
        "no sucede con Julietta (<code>bJ = 0.2</code>)"
    )

    #store model
    context.user_data['model'] = asymmetric

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SOLVE_OR_EDIT_TUTORIAL

async def scenario_spiral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Presents the spiral model"""
    #log
    logger.info("User %s chose the spiral scenario", update.message.from_user.first_name)

    msg = (
        "En este caso tenemos a una Julietta muy enamorada de Romeo (<code>aR = 0.98, cJ = 0.98</code>), "
        "mientras un Romeo que le gusta como cualquier otra mujer atractiva (<code>aJ = 0.126, "
        "cR = 0.126</code>). La capacidad de ahorro de Julietta es baja por estar siempre "
        "invitando a Romeo (<code>mJ = 0.126</code>), mientras que Romeo tiene cierta capacidad "
        "de ahorro (<code>mR = 0.64</code>). Sin embargo, Romeo suele celar a sus amigas (<code>uR = 0.64</code>) "
        "mientras que Julietta no siente celos por él (<code>uJ = 0.1</code>). Esta situación "
        "genera alta inestabilidad emocional en ambos (<code>bR,J = 0.95</code>). El resto de "
        "los parámetros tienen un valor de <code>0.5</code>."
    )

    #store model
    context.user_data['model'] = spiral

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SOLVE_OR_EDIT_TUTORIAL


async def solve_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solve the current model"""
    #logs
    logger.info("User %s solved the model", update.message.from_user.first_name)

    #solve model
    sol = solve_model(context.user_data['model'])

    #plot model
    name = context.user_data['model'].name
    plot_model(name, sol, show=False, save=True)

    reply_markup=ReplyKeyboardMarkup(
            keyboards["edit"], one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="edit or cancel"
    )

    await update.message.reply_photo(name + ".png", reply_markup=reply_markup)

    return SOLVE_OR_EDIT_TUTORIAL

async def edit_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives the new initial conditions for the model"""
    #logs
    logger.info("User %s edited the model", update.message.from_user.first_name)

    await update.message.reply_text(
        "Introduce los nuevos valores iniciales separados por comas.",
        reply_markup=ReplyKeyboardRemove(),
    )

    return INPUT_IC_TUTORIAL
async def edit_ic_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modifies the initial conditions of the model"""

    #create new model
    old = context.user_data['model']
    m = create_model(old.name, love_func, old.t_span, update.message.text, t_eval=old.t_eval, p=old.p)
    context.user_data['model'] = m

    await update.message.reply_text(
        "Listo!",
        reply_markup=ReplyKeyboardMarkup(
            keyboards["solve_or_edit"], one_time_keyboard=True, resize_keyboard=True
        ),
    )

    return SOLVE_OR_EDIT_TUTORIAL


# utils
def rd_tutorial_msgs():
    """ Returns a list of messages for the tutorial """
    msgs = []

    msgs.append(    # 0
        "Welcome to Radioactive Decay tutorial! In this tutorial you will learn how to use the "
        "bot to solve a radioactive decay model.\nConsider a sample of material that contains <code>N(t)</code> "
        "atoms of a certain radioactive isotope at time <code>t</code>. It has been observed that a constant "
        "fraction of those radioactive atoms will spontaneously decay (into atoms of another element "
        "or into another isotope of the same element) during each unit of time. This is called radioactive decay. "
        "defined by the following differential equation:\n\n <code>dN/dt = -kN</code>\n\n where "
        "<code>k</code> is a positive constant: the decay rate of the isotope.\n\n "
        "Now, let's start by entering the variables of the equation.\n\n "
        "Type <code>N</code> to continue."
    )

    msgs.append(    # 1
        "Great! Now, enter the differential equation. Only the right side of the equation is needed. "
        "In this case just type:\n\n<code>-k * N</code>.\n\n"
    )

    msgs.append(    # 2
        "Well done! You are getting the hang of it. Now, enter the time span, this "
        "is the time interval in which we will plot the solution. Let's "
        "consider the time interval <code>[0, 10]</code>.\n\n"
    )

    msgs.append(    # 3
        "Perfect! Now, enter the initial conditions. This is the value of <code>N</code> at time <code>t=0</code>. "
        "We need this so we can find a solution curve satisfying both the differential equation and this initial "
        "condition. In this case, let's consider <code>N(0) = 100</code>.\n\n"
    )

    msgs.append(    # 4
        "Awesome! Now we will ask you the number of points to be plotted. A higher number of points will result in "
        "a smoother curve, but it will take longer to compute. <code>1000</code> points shall suffice.\n\n"
    )

    msgs.append(    # 5
        "Good job! Now let's decide on a value for the decay rate. This bot detects the parameters in the "
        "equations you enter, and will ask you for their values. In this case, the parameter is <code>k</code>. "
        "Let's consider <code>k = 0.5</code>.\n\n"
    )

    msgs.append(    # 6
        "That's it! Now you can solve the model by typing <code>/solve</code>.\n\n"
        "Or you can also edit it if you want to, I bet you can figure it out by yourself.\n\n"
    )

    return msgs


# ------------------ #
#  MAIN APPLICATION  #
# ------------------ #

def main():
    """Run bot."""
    app = Application.builder().token(TOKEN).read_timeout(30).write_timeout(30).build()

    # define handlers
    start_handler = CommandHandler("start", start)
    tutorial_handler = CommandHandler("tutorial", tutorial)

    create_handler = ConversationHandler(
        entry_points=[
            CommandHandler("create", create),
            MessageHandler(filters.Regex(r"^Radioactive decay$"), tutorial_choice)
            ],
        states={
            VARIABLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_variables)],
            EQUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_equation)],
            TS_IC: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_time_interval)],
            PARAMETERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_parameters)],
            SOLVE_OR_EDIT: [MessageHandler(filters.Regex(r"^solve$"), solve), MessageHandler(filters.Regex(r"^edit$"), edit)],
            EDIT: [MessageHandler(filters.Regex(r"^parameters$|^initial conditions$|^time interval$|^number of points$"), input_edit)],
            EDITED: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_model)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    rj_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^Romeo and Juliet$"), rj)],
        states={
            SCENARIO: [MessageHandler(filters.Regex(r"^Relación ideal$"), scenario_ideal), MessageHandler(filters.Regex(r"^Relación asimétrica$"), scenario_asymmetric), MessageHandler(filters.Regex(r"^Relación espiral$"), scenario_spiral)],
            SOLVE_OR_EDIT_TUTORIAL: [MessageHandler(filters.Regex(r"^solve$"), solve_tutorial), MessageHandler(filters.Regex(r"^edit$"), edit_tutorial)],
            INPUT_IC_TUTORIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_ic_tutorial)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


    # add handlers
    app.add_handler(start_handler)
    app.add_handler(create_handler)
    app.add_handler(rj_handler)
    app.add_handler(tutorial_handler)
    app.add_error_handler(error_handler)


    # start the bot (ctrl-c to stop)
    app.run_polling()


if __name__ == "__main__":
    main()

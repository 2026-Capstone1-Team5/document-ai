# Chapter 1

# Mechanics

# 1.1 Point-kinetics in a fixed coordinate system

# 1.1.1 Definitions

The position $\vec { r }$ , the velocity $\vec { v }$ and the acceleration $\vec { a }$ are defined by: $\vec { r } = ( x , y , z ) , \ : \vec { v } = ( \dot { x } , \dot { y } , \dot { z } )$ , $\vec { a } = ( \ddot { x } , \ddot { y } , \ddot { z } )$ . The following holds:

$$
s ( t ) = s _ { 0 } + \int | \vec { v } ( t ) | d t \ ; \quad \vec { r } ( t ) = \vec { r } _ { 0 } + \int \vec { v } ( t ) d t \ ; \quad \vec { v } ( t ) = \vec { v } _ { 0 } + \int \vec { a } ( t ) d t
$$

When the acceleration is constant this gives: $v ( t ) = v _ { 0 } + a t$ and $\begin{array} { r } { s ( t ) = s _ { 0 } + v _ { 0 } t + \frac { 1 } { 2 } a t ^ { 2 } } \end{array}$ . For the unit vectors in a direction $\perp$ to the orbit $\vec { e _ { \mathrm { t } } }$ and parallel to it $\vec { e } _ { \mathrm { n } }$ holds:

$$
\vec { e } _ { \mathrm { t } } = \frac { \vec { v } } { \vert \vec { v } \vert } = \frac { d \vec { r } } { d s } \quad \dot { \vec { e } } _ { \mathrm { t } } = \frac { v } { \rho } \vec { e } _ { \mathrm { n } } \ ; \quad \vec { e } _ { \mathrm { n } } = \frac { \dot { \vec { e } } _ { \mathrm { t } } } { \vert \dot { \vec { e } } _ { \mathrm { t } } \vert }
$$

For the curvature $k$ and the radius of curvature $\rho$ holds:

$$
{ \vec { k } } = { \frac { d { \vec { e _ { \mathrm { t } } } } } { d s } } = { \frac { d ^ { 2 } { \vec { r } } } { d s ^ { 2 } } } = \left| { \frac { d \varphi } { d s } } \right| ~ ; \quad \rho = { \frac { 1 } { | k | } }
$$

# 1.1.2 Polar coordinates

Polar coordinates are defined by: $x = r \cos ( \theta )$ , $y = r \sin ( \theta )$ . So, for the unit coordinate vectors holds: ${ \dot { \vec { e } } } _ { r } = { \dot { \theta } } { \vec { e } } _ { \theta }$ , ${ \dot { \vec { e _ { \theta } } } } = - { \dot { \theta } } { \vec { e _ { r } } }$

The velocity and the acceleration are derived from: $\vec { r } = r \vec { e } _ { r }$ , ${ \vec { v } } = { \dot { r } } { \vec { e } } _ { r } + r { \dot { \theta } } { \vec { e } } _ { \theta }$ , $\vec { a } = ( \ddot { r } - r \dot { \theta } ^ { 2 } ) \vec { e } _ { r } + ( 2 \dot { r } \dot { \theta } +$ $r { \ddot { \theta } } ) { \vec { e } } _ { \theta }$ .

# 1.2 Relative motion

For the motion of a point D w.r.t. a point Q holds: ${ \vec { r } } _ { \mathrm { D } } = { \vec { r } } _ { \mathrm { Q } } + { \frac { { \vec { \omega } } \times { \vec { v } } _ { \mathrm { Q } } } { \omega ^ { 2 } } }$ with $\mathrm { Q } \mathrm { \vec { D } } = { \vec { r } } _ { \mathrm { D } } - { \vec { r } } _ { \mathrm { Q } }$ and $\omega = { \dot { \theta } }$

Further holds: $\alpha = { \ddot { \theta } }$ . ′ means that the quantity is defined in a moving system of coordinates. In a moving system holds:

${ \vec { v } } = { \vec { v } } _ { \mathrm { Q } } + { \vec { v } } ^ { \prime } + { \vec { \omega } } \times { \vec { r } } ^ { \prime }$ and ${ \vec { a } } = { \vec { a } } _ { \mathrm { Q } } + { \vec { a } } ^ { \prime } + { \vec { \alpha } } \times { \vec { r } } ^ { \prime } + 2 { \vec { \omega } } \times { \vec { v } } - { \vec { \omega } } \times ( { \vec { \omega } } \times { \vec { r } } ^ { \prime } )$ with $| \vec { \omega } \times ( \vec { \omega } \times \vec { r } ^ { \prime } ) | = \omega ^ { 2 } \vec { r } _ { n }$ ′

# 1.3 Point-dynamics in a fixed coordinate system

# 1.3.1 Force, (angular)momentum and energy

Newton’s 2nd law connects the force on an object and the resulting acceleration of the object:

$$
\vec { F } ( \vec { r } , \vec { v } , t ) = m \vec { a } = \frac { d \vec { p } } { d t } , \mathrm { ~ w h e r e ~ t h e ~ } m o m e n t u m \mathrm { ~ i s ~ g i v e n ~ b y : ~ } \vec { p } = m \vec { v }
$$

Newton’s 3rd law is: $\vec { F } _ { \mathrm { a c t i o n } } = - \vec { F } _ { \mathrm { r e a c t i o n } }$

For the power $P$ holds: $P = \dot { W } = \vec { F } \cdot \vec { v }$ . For the total energy $W$ , the kinetic energy $T$ and the potential energy $U$ holds: $W = T + U ~ ; ~ \dot { T } = - \dot { U }$ with $\scriptstyle T = { \frac { 1 } { 2 } } m v ^ { 2 }$ .

The kick $\vec { S }$ is given by: $\vec { S } = \Delta \vec { p } = \int \vec { F } d t$

The work $A$ , delivered by a force, is $A = \int _ { 1 } ^ { 2 } { \vec { F } } \cdot d { \vec { s } } = \int _ { 1 } ^ { 2 } F \cos ( \alpha ) d s$

The torque $\vec { \tau }$ is related to the angular momentum $\vec { L }$ : $\vec { \tau } = \dot { \vec { L } } = \vec { r } \times \vec { F }$ ; and ${ \vec { L } } = { \vec { r } } \times { \vec { p } } = m { \vec { v } } \times { \vec { r } }$ , $| \vec { L } | = m r ^ { 2 } \omega$ . The following holds:

$$
\tau = - { \frac { \partial U } { \partial \theta } }
$$

So, the conditions for a mechanical equilibrium are: $\begin{array} { r } { \sum \vec { F } _ { i } = 0 } \end{array}$ and $\sum \vec { \tau } _ { i } = 0$ .

The force of friction is usually proportional with the force perpendicular to the surface, except when the motion starts, when a threshold has to be overcome: $F _ { \mathrm { f r i c } } = f \cdot F _ { \mathrm { n o r m } } \cdot \vec { e } _ { \mathrm { t } }$ .

# 1.3.2 Conservative force fields

A conservative force can be written as the gradient of a potential: $\vec { F } _ { \mathrm { c o n s } } = - \vec { \nabla } U$ . From this follows that $\mathrm { r o t } \vec { F } = \vec { 0 }$ . For such a force field also holds:

$$
\oint { \vec { F } } \cdot d { \vec { s } } = 0 \Rightarrow U = U _ { 0 } - \int _ { r _ { 0 } } ^ { r _ { 1 } } { \vec { F } } \cdot d { \vec { s } }
$$

So the work delivered by a conservative force field depends not on the followed trajectory but only on the starting and ending points of the motion.

# 1.3.3 Gravitation

The Newtonian law of gravitation is (in GRT one also uses $\kappa$ instead of $G$ ):

$$
{ \vec { F } } _ { \mathrm { g } } = - G { \frac { m _ { 1 } m _ { 2 } } { r ^ { 2 } } } { \vec { e } } _ { r }
$$

The gravitationpotential is then given by $V = - G m / r$ . From Gauss law then follows: $\nabla ^ { 2 } V = 4 \pi G \varrho$

# 1.3.4 Orbital equations

From the equations of Lagrange for $\phi$ , conservation of angular momentum can be derived:

$$
{ \frac { \partial { \mathcal { L } } } { \partial \phi } } = { \frac { \partial V } { \partial \phi } } = 0 \Rightarrow { \frac { d } { d t } } ( m r ^ { 2 } \phi ) = 0 \Rightarrow L _ { z } = m r ^ { 2 } \phi = \mathrm { c o n s t a n t }
$$

For the radius as a function of time can be found that:

$$
\left( { \frac { d r } { d t } } \right) ^ { 2 } = { \frac { 2 ( W - V ) } { m } } - { \frac { L ^ { 2 } } { m ^ { 2 } r ^ { 2 } } }
$$

The angular equation is then:

$$
\phi - \phi _ { 0 } = \int _ { 0 } ^ { r } \left[ \frac { m r ^ { 2 } } { L } \sqrt { \frac { 2 ( W - V ) } { m } - \frac { L ^ { 2 } } { m ^ { 2 } r ^ { 2 } } } \right] ^ { - 1 } d r \stackrel { r ^ { - 2 } \mathrm { f e l d } } { = } \operatorname { a r c c o s } \left( 1 + { \frac { \frac { 1 } { r } - \frac { 1 } { r _ { 0 } } } { \frac { 1 } { r _ { 0 } } + k m / L _ { z } ^ { 2 } } } \right)
$$

if $\boldsymbol { F } = \boldsymbol { F } ( \boldsymbol { r } )$ : $L =$ constant, if $F$ is conservative: $W =$ constant, if $\vec { F } \perp \vec { v }$ then $\Delta T = 0$ and $U = 0$ .

# Kepler’s equations

In a force field $\boldsymbol { F } = \boldsymbol { k } \boldsymbol { r } ^ { - 2 }$ , the orbits are conic sections (Kepler’s 1st law). The equation of the orbit is:

$$
r ( \theta ) = \frac { \ell } { 1 + \varepsilon \cos ( \theta - \theta _ { 0 } ) } ~ , ~ \mathrm { o r } ; ~ x ^ { 2 } + y ^ { 2 } = ( \ell - \varepsilon x ) ^ { 2 }
$$

with

$$
\ell = \frac { L ^ { 2 } } { G \mu ^ { 2 } M _ { \mathrm { t o t } } } ~ ; \quad \varepsilon ^ { 2 } = 1 + \frac { 2 W L ^ { 2 } } { G ^ { 2 } \mu ^ { 3 } M _ { \mathrm { t o t } } ^ { 2 } } = 1 - \frac { \ell } { a } ~ ; \quad a = \frac { \ell } { 1 - \varepsilon ^ { 2 } } = \frac { k } { 2 W }
$$

$a$ is half the length of the long axis of the elliptical orbit in case the orbit is closed. Half the length of the short axis is $b = { \sqrt { a \ell } }$ . $\varepsilon$ is the excentricity of the orbit. Orbits with an equal $\varepsilon$ are equally shaped. Now, 5 kinds of orbits are possible:

1. $k < 0$ and $\varepsilon = 0$ : a circle.

2. $k < 0$ and $0 < \varepsilon < 1$ : an ellipse.

3. $k < 0$ and $\varepsilon = 1$ : a parabole.

4. $k < 0$ and $\varepsilon > 1$ : a hyperbole, curved towards the center of force.

5. $k > 0$ and $\varepsilon > 1$ : a hyperbole, curved away of the center of force.

Other combinations are not possible: the total energy in a repulsive force field is always positive so $\varepsilon > 1$ .

If the surface between the orbit walked thru between $t _ { 1 }$ and $t _ { 2 }$ and the focus C around which the planet moves is $A ( t _ { 1 } , t _ { 2 } )$ , Kepler’s 2nd law is

$$
A ( t _ { 1 } , t _ { 2 } ) = \frac { L _ { \mathrm { C } } } { 2 m } ( t _ { 2 } - t _ { 1 } )
$$

Kepler’s 3rd law is, with $T$ the period and $M _ { \mathrm { t o t } }$ the total mass of the system:

$$
{ \frac { T ^ { 2 } } { a ^ { 3 } } } = { \frac { 4 \pi ^ { 2 } } { G M _ { \mathrm { t o t } } } }
$$

# 1.3.5 The virial theorem

The virial theorem for one particle is:

$$
\left. m { \vec { v } } \cdot { \vec { r } } \right. = 0 \Rightarrow \left. T \right. = - { \textstyle { \frac { 1 } { 2 } } } \left. { \vec { F } } \cdot { \vec { r } } \right. = { \textstyle { \frac { 1 } { 2 } } } \left. r { \frac { d U } { d r } } \right. = { \textstyle { \frac { 1 } { 2 } } } n \left. U \right. { \mathrm { ~ i f ~ } } U = - { \textstyle { \frac { k } { r ^ { n } } } }
$$

The virial theorem for a collection of particles is:

$$
\begin{array} { r } { \langle T \rangle = - \frac { 1 } { 2 } \left. \displaystyle \sum _ { \mathrm { p a r t i c l e s } } \vec { F _ { i } } \cdot \vec { r _ { i } } + \sum _ { \mathrm { p a i r s } } \vec { F _ { i j } } \cdot \vec { r } _ { i j } \right. } \end{array}
$$

These propositions can also be written as: $2 E _ { \mathrm { k i n } } + E _ { \mathrm { p o t } } = 0$ .

# 1.4 Point dynamics in a moving coordinate system

# 1.4.1 Apparent forces

The total force in a moving coordinate system can be found by subtracting the apparent forces from the forces working in the reference frame: $\vec { F } ^ { \ \prime } = \vec { F } - \vec { F } _ { \mathrm { a p p } }$ . The different apparent forces are given by:

1. Transformation of the origin: $F _ { \mathrm { o r } } = - m { \vec { a } } _ { a }$
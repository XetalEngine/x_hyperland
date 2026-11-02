/*
 * Copyright © 2005 Novell, Inc.
 *
 * Permission to use, copy, modify, distribute, and sell this software
 * and its documentation for any purpose is hereby granted without
 * fee, provided that the above copyright notice appear in all copies
 * and that both that copyright notice and this permission notice
 * appear in supporting documentation, and that the name of
 * Novell, Inc. not be used in advertising or publicity pertaining to
 * distribution of the software without specific, written prior permission.
 * Novell, Inc. makes no representations about the suitability of this
 * software for any purpose. It is provided "as is" without express or
 * implied warranty.
 *
 * NOVELL, INC. DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
 * INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
 * NO EVENT SHALL NOVELL, INC. BE LIABLE FOR ANY SPECIAL, INDIRECT OR
 * CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
 * OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
 * NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION
 * WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * Author: David Reveman <davidr@novell.com>
 */


// Original Compiz core/plugins/wobbly.c math and edge resistance.
// Host geometry replaces X11 screen/window lookup; allocation uses C++ casts.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>
namespace Wobbly::Compiz {

using Bool = bool;
constexpr bool TRUE = true, FALSE = false;
constexpr int MAXSHORT = 32767, MINSHORT = -32768;
constexpr unsigned CompWindowTypeNormalMask=1, CompWindowTypeToolbarMask=2,
                   CompWindowTypeMenuMask=4, CompWindowTypeUtilMask=8;
constexpr unsigned SNAP_WINDOW_TYPE=15;
constexpr int WobblyInitial=1, WobblyForce=2, WobblyVelocity=4;
struct XRectangle { int x=0,y=0,width=0,height=0; };
struct CompOutput { XRectangle workArea; };
struct CompStruts { XRectangle left,right,top,bottom; };
struct CompWindow;
struct CompScreen { std::vector<CompOutput> outputDev; CompWindow* windows=nullptr; };
struct Extents { int left=0,right=0,top=0,bottom=0; };
struct CompWindow {
    XRectangle attrib;
    int width=0,height=0;
    Extents output,input;
    CompScreen* screen=nullptr;
    CompWindow* next=nullptr;
    CompStruts* struts=nullptr;
    bool mapNum=true,invisible=false;
    unsigned type=CompWindowTypeNormalMask;
};
inline int outputDeviceForPoint(CompScreen* screen,float x,float y) {
    int best=0;double distance=1e30;
    for(size_t i=0;i<screen->outputDev.size();++i){
        const auto& b=screen->outputDev[i].workArea;
        const double dx=x-std::clamp(x,float(b.x),float(b.x+b.width));
        const double dy=y-std::clamp(y,float(b.y),float(b.y+b.height));
        if(dx*dx+dy*dy<distance){distance=dx*dx+dy*dy;best=i;}
    }
    return best;
}
constexpr auto GRID_WIDTH = 4;
constexpr auto GRID_HEIGHT = 4;

constexpr auto MODEL_MAX_SPRINGS = (GRID_WIDTH * GRID_HEIGHT * 2);

constexpr auto MASS = 15.0f;

typedef struct _xy_pair {
    float x, y;
} Point, Vector;

constexpr auto NorthEdgeMask = (1L << 0);
constexpr auto SouthEdgeMask = (1L << 1);
constexpr auto WestEdgeMask = (1L << 2);
constexpr auto EastEdgeMask = (1L << 3);

constexpr auto EDGE_DISTANCE = 25.0f;
constexpr auto EDGE_VELOCITY = 13.0f;

typedef struct _Edge {
    float next, prev;

    float start;
    float end;

    float attract;
    float velocity;

    Bool  snapped;
} Edge;

typedef struct _Object {
    Vector	 force;
    Point	 position;
    Vector	 velocity;
    float	 theta;
    Bool	 immobile;
    unsigned int edgeMask;
    Edge	 vertEdge;
    Edge	 horzEdge;
} Object;

typedef struct _Spring {
    Object *a;
    Object *b;
    Vector offset;
} Spring;

constexpr auto NORTH = 0;
constexpr auto SOUTH = 1;
constexpr auto WEST = 2;
constexpr auto EAST = 3;

typedef struct _Model {
    Object	 *objects;
    int		 numObjects;
    Spring	 springs[MODEL_MAX_SPRINGS];
    int		 numSprings;
    Object	 *anchorObject;
    float	 steps;
    Point	 topLeft;
    Point	 bottomRight;
    unsigned int edgeMask;
    unsigned int snapCnt[4];
} Model;

static void
findNextWestEdge (CompWindow *w,
		  Object     *object)
{
    int v, v1, v2;
    int s, start;
    int e, end;
    int x;
    int output;
    const XRectangle *workArea;
    int workAreaEdge;

    start = -65535.0f;
    end   =  65535.0f;

    v1 = -65535.0f;
    v2 =  65535.0f;

    x = object->position.x + w->output.left - w->input.left;

    output = outputDeviceForPoint (w->screen, x, object->position.y);
    workArea = &w->screen->outputDev[output].workArea;
    workAreaEdge = workArea->x;

    if (x >= workAreaEdge)
    {
	CompWindow *p;

	v1 = workAreaEdge;

	for (p = w->screen->windows; p; p = p->next)
	{
	    if (w == p)
		continue;

	    if (p->mapNum && p->struts)
	    {
		s = p->struts->left.y - w->output.top;
		e = p->struts->left.y + p->struts->left.height +
		    w->output.bottom;
	    }
	    else if (!p->invisible && (p->type & SNAP_WINDOW_TYPE))
	    {
		s = p->attrib.y - p->input.top - w->output.top;
		e = p->attrib.y + p->height + p->input.bottom +
		    w->output.bottom;
	    }
	    else
	    {
		continue;
	    }

	    if (s > object->position.y)
	    {
		if (s < end)
		    end = s;
	    }
	    else if (e < object->position.y)
	    {
		if (e > start)
		    start = e;
	    }
	    else
	    {
		if (s > start)
		    start = s;

		if (e < end)
		    end = e;

		if (p->mapNum && p->struts)
		    v = p->struts->left.x + p->struts->left.width;
		else
		    v = p->attrib.x + p->width + p->input.right;

		if (v <= x)
		{
		    if (v > v1)
			v1 = v;
		}
		else
		{
		    if (v < v2)
			v2 = v;
		}
	    }
	}
    }
    else
    {
	v2 = workAreaEdge;
    }

    v1 = v1 - w->output.left + w->input.left;
    v2 = v2 - w->output.left + w->input.left;

    if (v1 != (int) object->vertEdge.next)
	object->vertEdge.snapped = FALSE;

    object->vertEdge.start = start;
    object->vertEdge.end   = end;

    object->vertEdge.next = v1;
    object->vertEdge.prev = v2;

    object->vertEdge.attract  = v1 + EDGE_DISTANCE;
    object->vertEdge.velocity = EDGE_VELOCITY;
}

static void
findNextEastEdge (CompWindow *w,
		  Object     *object)
{
    int v, v1, v2;
    int s, start;
    int e, end;
    int x;
    int output;
    const XRectangle *workArea;
    int workAreaEdge;

    start = -65535.0f;
    end   =  65535.0f;

    v1 =  65535.0f;
    v2 = -65535.0f;

    x = object->position.x - w->output.right + w->input.right;

    output = outputDeviceForPoint (w->screen, x, object->position.y);
    workArea = &w->screen->outputDev[output].workArea;
    workAreaEdge = workArea->x + workArea->width;

    if (x <= workAreaEdge)
    {
	CompWindow *p;

	v1 = workAreaEdge;

	for (p = w->screen->windows; p; p = p->next)
	{
	    if (w == p)
		continue;

	    if (p->mapNum && p->struts)
	    {
		s = p->struts->right.y - w->output.top;
		e = p->struts->right.y + p->struts->right.height +
		    w->output.bottom;
	    }
	    else if (!p->invisible && (p->type & SNAP_WINDOW_TYPE))
	    {
		s = p->attrib.y - p->input.top - w->output.top;
		e = p->attrib.y + p->height + p->input.bottom +
		    w->output.bottom;
	    }
	    else
	    {
		continue;
	    }

	    if (s > object->position.y)
	    {
		if (s < end)
		    end = s;
	    }
	    else if (e < object->position.y)
	    {
		if (e > start)
		    start = e;
	    }
	    else
	    {
		if (s > start)
		    start = s;

		if (e < end)
		    end = e;

		if (p->mapNum && p->struts)
		    v = p->struts->right.x;
		else
		    v = p->attrib.x - p->input.left;

		if (v >= x)
		{
		    if (v < v1)
			v1 = v;
		}
		else
		{
		    if (v > v2)
			v2 = v;
		}
	    }
	}
    }
    else
    {
	v2 = workAreaEdge;
    }

    v1 = v1 + w->output.right - w->input.right;
    v2 = v2 + w->output.right - w->input.right;

    if (v1 != (int) object->vertEdge.next)
	object->vertEdge.snapped = FALSE;

    object->vertEdge.start = start;
    object->vertEdge.end   = end;

    object->vertEdge.next = v1;
    object->vertEdge.prev = v2;

    object->vertEdge.attract  = v1 - EDGE_DISTANCE;
    object->vertEdge.velocity = EDGE_VELOCITY;
}

static void
findNextNorthEdge (CompWindow *w,
		   Object     *object)
{
    int v, v1, v2;
    int s, start;
    int e, end;
    int y;
    int output;
    const XRectangle *workArea;
    int workAreaEdge;

    start = -65535.0f;
    end   =  65535.0f;

    v1 = -65535.0f;
    v2 =  65535.0f;

    y = object->position.y + w->output.top - w->input.top;

    output = outputDeviceForPoint (w->screen, object->position.x, y);
    workArea = &w->screen->outputDev[output].workArea;
    workAreaEdge = workArea->y;

    if (y >= workAreaEdge)
    {
	CompWindow *p;

	v1 = workAreaEdge;

	for (p = w->screen->windows; p; p = p->next)
	{
	    if (w == p)
		continue;

	    if (p->mapNum && p->struts)
	    {
		s = p->struts->top.x - w->output.left;
		e = p->struts->top.x + p->struts->top.width + w->output.right;
	    }
	    else if (!p->invisible && (p->type & SNAP_WINDOW_TYPE))
	    {
		s = p->attrib.x - p->input.left - w->output.left;
		e = p->attrib.x + p->width + p->input.right + w->output.right;
	    }
	    else
	    {
		continue;
	    }

	    if (s > object->position.x)
	    {
		if (s < end)
		    end = s;
	    }
	    else if (e < object->position.x)
	    {
		if (e > start)
		    start = e;
	    }
	    else
	    {
		if (s > start)
		    start = s;

		if (e < end)
		    end = e;

		if (p->mapNum && p->struts)
		    v = p->struts->top.y + p->struts->top.height;
		else
		    v = p->attrib.y + p->height + p->input.bottom;

		if (v <= y)
		{
		    if (v > v1)
			v1 = v;
		}
		else
		{
		    if (v < v2)
			v2 = v;
		}
	    }
	}
    }
    else
    {
	v2 = workAreaEdge;
    }

    v1 = v1 - w->output.top + w->input.top;
    v2 = v2 - w->output.top + w->input.top;

    if (v1 != (int) object->horzEdge.next)
	object->horzEdge.snapped = FALSE;

    object->horzEdge.start = start;
    object->horzEdge.end   = end;

    object->horzEdge.next = v1;
    object->horzEdge.prev = v2;

    object->horzEdge.attract  = v1 + EDGE_DISTANCE;
    object->horzEdge.velocity = EDGE_VELOCITY;
}

static void
findNextSouthEdge (CompWindow *w,
		   Object     *object)
{
    int v, v1, v2;
    int s, start;
    int e, end;
    int y;
    int output;
    const XRectangle *workArea;
    int workAreaEdge;

    start = -65535.0f;
    end   =  65535.0f;

    v1 =  65535.0f;
    v2 = -65535.0f;

    y = object->position.y - w->output.bottom + w->input.bottom;

    output = outputDeviceForPoint (w->screen, object->position.x, y);
    workArea = &w->screen->outputDev[output].workArea;
    workAreaEdge = workArea->y + workArea->height;

    if (y <= workAreaEdge)
    {
	CompWindow *p;

	v1 = workAreaEdge;

	for (p = w->screen->windows; p; p = p->next)
	{
	    if (w == p)
		continue;

	    if (p->mapNum && p->struts)
	    {
		s = p->struts->bottom.x - w->output.left;
		e = p->struts->bottom.x + p->struts->bottom.width +
		    w->output.right;
	    }
	    else if (!p->invisible && (p->type & SNAP_WINDOW_TYPE))
	    {
		s = p->attrib.x - p->input.left - w->output.left;
		e = p->attrib.x + p->width + p->input.right + w->output.right;
	    }
	    else
	    {
		continue;
	    }

	    if (s > object->position.x)
	    {
		if (s < end)
		    end = s;
	    }
	    else if (e < object->position.x)
	    {
		if (e > start)
		    start = e;
	    }
	    else
	    {
		if (s > start)
		    start = s;

		if (e < end)
		    end = e;

		if (p->mapNum && p->struts)
		    v = p->struts->bottom.y;
		else
		    v = p->attrib.y - p->input.top;

		if (v >= y)
		{
		    if (v < v1)
			v1 = v;
		}
		else
		{
		    if (v > v2)
			v2 = v;
		}
	    }
	}
    }
    else
    {
	v2 = workAreaEdge;
    }

    v1 = v1 + w->output.bottom - w->input.bottom;
    v2 = v2 + w->output.bottom - w->input.bottom;

    if (v1 != (int) object->horzEdge.next)
	object->horzEdge.snapped = FALSE;

    object->horzEdge.start = start;
    object->horzEdge.end   = end;

    object->horzEdge.next = v1;
    object->horzEdge.prev = v2;

    object->horzEdge.attract  = v1 - EDGE_DISTANCE;
    object->horzEdge.velocity = EDGE_VELOCITY;
}

static void
objectInit (Object *object,
	    float  positionX,
	    float  positionY,
	    float  velocityX,
	    float  velocityY)
{
    object->force.x = 0;
    object->force.y = 0;

    object->position.x = positionX;
    object->position.y = positionY;

    object->velocity.x = velocityX;
    object->velocity.y = velocityY;

    object->theta    = 0;
    object->immobile = FALSE;

    object->edgeMask = 0;

    object->vertEdge.snapped = FALSE;
    object->horzEdge.snapped = FALSE;

    object->vertEdge.next = 0.0f;
    object->horzEdge.next = 0.0f;
}

static void
springInit (Spring *spring,
	    Object *a,
	    Object *b,
	    float  offsetX,
	    float  offsetY)
{
    spring->a	     = a;
    spring->b	     = b;
    spring->offset.x = offsetX;
    spring->offset.y = offsetY;
}

static void
modelCalcBounds (Model *model)
{
    int i;

    model->topLeft.x	 = MAXSHORT;
    model->topLeft.y	 = MAXSHORT;
    model->bottomRight.x = MINSHORT;
    model->bottomRight.y = MINSHORT;

    for (i = 0; i < model->numObjects; i++)
    {
	if (model->objects[i].position.x < model->topLeft.x)
	    model->topLeft.x = model->objects[i].position.x;
	else if (model->objects[i].position.x > model->bottomRight.x)
	    model->bottomRight.x = model->objects[i].position.x;

	if (model->objects[i].position.y < model->topLeft.y)
	    model->topLeft.y = model->objects[i].position.y;
	else if (model->objects[i].position.y > model->bottomRight.y)
	    model->bottomRight.y = model->objects[i].position.y;
    }
}

static void
modelAddSpring (Model  *model,
		Object *a,
		Object *b,
		float  offsetX,
		float  offsetY)
{
    Spring *spring;

    spring = &model->springs[model->numSprings];
    model->numSprings++;

    springInit (spring, a, b, offsetX, offsetY);
}

static void
modelSetMiddleAnchor (Model *model,
		      int   x,
		      int   y,
		      int   width,
		      int   height)
{
    float gx, gy;

    gx = ((GRID_WIDTH  - 1) / 2 * width)  / (float) (GRID_WIDTH  - 1);
    gy = ((GRID_HEIGHT - 1) / 2 * height) / (float) (GRID_HEIGHT - 1);

    if (model->anchorObject)
	model->anchorObject->immobile = FALSE;

    model->anchorObject = &model->objects[GRID_WIDTH *
					  ((GRID_HEIGHT - 1) / 2) +
					  (GRID_WIDTH - 1) / 2];
    model->anchorObject->position.x = x + gx;
    model->anchorObject->position.y = y + gy;

    model->anchorObject->immobile = TRUE;
}

static void
modelSetTopAnchor (Model *model,
		   int   x,
		   int   y,
		   int   width)
{
    float gx;

    gx = ((GRID_WIDTH - 1) / 2 * width)  / (float) (GRID_WIDTH - 1);

    if (model->anchorObject)
	model->anchorObject->immobile = FALSE;

    model->anchorObject = &model->objects[(GRID_WIDTH - 1) / 2];
    model->anchorObject->position.x = x + gx;
    model->anchorObject->position.y = y;

    model->anchorObject->immobile = TRUE;
}

static void
modelAddEdgeAnchors (Model *model,
		     int   x,
		     int   y,
		     int   width,
		     int   height)
{
    Object *o;

    o = &model->objects[0];
    o->position.x = x;
    o->position.y = y;
    o->immobile = TRUE;

    o = &model->objects[GRID_WIDTH - 1];
    o->position.x = x + width;
    o->position.y = y;
    o->immobile = TRUE;

    o = &model->objects[GRID_WIDTH * (GRID_HEIGHT - 1)];
    o->position.x = x;
    o->position.y = y + height;
    o->immobile = TRUE;

    o = &model->objects[model->numObjects - 1];
    o->position.x = x + width;
    o->position.y = y + height;
    o->immobile = TRUE;

    if (!model->anchorObject)
	model->anchorObject = &model->objects[0];
}

static void
modelRemoveEdgeAnchors (Model *model,
			int   x,
			int   y,
			int   width,
			int   height)
{
    Object *o;

    o = &model->objects[0];
    o->position.x = x;
    o->position.y = y;
    if (o != model->anchorObject)
	o->immobile = FALSE;

    o = &model->objects[GRID_WIDTH - 1];
    o->position.x = x + width;
    o->position.y = y;
    if (o != model->anchorObject)
	o->immobile = FALSE;

    o = &model->objects[GRID_WIDTH * (GRID_HEIGHT - 1)];
    o->position.x = x;
    o->position.y = y + height;
    if (o != model->anchorObject)
	o->immobile = FALSE;

    o = &model->objects[model->numObjects - 1];
    o->position.x = x + width;
    o->position.y = y + height;
    if (o != model->anchorObject)
	o->immobile = FALSE;
}

static void
modelAdjustObjectPosition (Model  *model,
			   Object *object,
			   int    x,
			   int    y,
			   int    width,
			   int    height)
{
    Object *o;
    int	   gridX, gridY, i = 0;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    o = &model->objects[i];
	    if (o == object)
	    {
		o->position.x = x + (gridX * width) / (GRID_WIDTH - 1);
		o->position.y = y + (gridY * height) / (GRID_HEIGHT - 1);

		return;
	    }

	    i++;
	}
    }
}

static void
modelInitObjects (Model *model,
		  int	x,
		  int   y,
		  int	width,
		  int	height)
{
    int	  gridX, gridY, i = 0;
    float gw, gh;

    gw = GRID_WIDTH  - 1;
    gh = GRID_HEIGHT - 1;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    objectInit (&model->objects[i],
			x + (gridX * width) / gw,
			y + (gridY * height) / gh,
			0, 0);
	    i++;
	}
    }

    modelSetMiddleAnchor (model, x, y, width, height);
}

static void
modelUpdateSnapping (CompWindow *window,
		     Model      *model)
{
    unsigned int edgeMask, gridMask, mask;
    int		 gridX, gridY, i = 0;

    edgeMask = model->edgeMask;

    if (model->snapCnt[NORTH])
	edgeMask &= ~SouthEdgeMask;
    else if (model->snapCnt[SOUTH])
	edgeMask &= ~NorthEdgeMask;

    if (model->snapCnt[WEST])
	edgeMask &= ~EastEdgeMask;
    else if (model->snapCnt[EAST])
	edgeMask &= ~WestEdgeMask;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	if (gridY == 0)
	    gridMask = edgeMask & NorthEdgeMask;
	else if (gridY == GRID_HEIGHT - 1)
	    gridMask = edgeMask & SouthEdgeMask;
	else
	    gridMask = 0;

	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    mask = gridMask;

	    if (gridX == 0)
		mask |= edgeMask & WestEdgeMask;
	    else if (gridX == GRID_WIDTH - 1)
		mask |= edgeMask & EastEdgeMask;

	    if (mask != model->objects[i].edgeMask)
	    {
		model->objects[i].edgeMask = mask;

		if (mask & WestEdgeMask)
		{
		    if (!model->objects[i].vertEdge.snapped)
			findNextWestEdge (window, &model->objects[i]);
		}
		else if (mask & EastEdgeMask)
		{
		    if (!model->objects[i].vertEdge.snapped)
			findNextEastEdge (window, &model->objects[i]);
		}
		else
		    model->objects[i].vertEdge.snapped = FALSE;

		if (mask & NorthEdgeMask)
		{
		    if (!model->objects[i].horzEdge.snapped)
			findNextNorthEdge (window, &model->objects[i]);
		}
		else if (mask & SouthEdgeMask)
		{
		    if (!model->objects[i].horzEdge.snapped)
			findNextSouthEdge (window, &model->objects[i]);
		}
		else
		    model->objects[i].horzEdge.snapped = FALSE;
	    }

	    i++;
	}
    }
}

static void
modelReduceEdgeEscapeVelocity (Model *model)
{
    int	gridX, gridY, i = 0;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    if (model->objects[i].vertEdge.snapped)
		model->objects[i].vertEdge.velocity *= drand48 () * 0.25f;

	    if (model->objects[i].horzEdge.snapped)
		model->objects[i].horzEdge.velocity *= drand48 () * 0.25f;

	    i++;
	}
    }
}

static Bool
modelDisableSnapping (CompWindow *window,
		      Model      *model)
{
    int	 gridX, gridY, i = 0;
    Bool snapped = FALSE;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    if (model->objects[i].vertEdge.snapped ||
		model->objects[i].horzEdge.snapped)
		snapped = TRUE;

	    model->objects[i].vertEdge.snapped = FALSE;
	    model->objects[i].horzEdge.snapped = FALSE;

	    model->objects[i].edgeMask = 0;

	    i++;
	}
    }

    memset (model->snapCnt, 0, sizeof (model->snapCnt));

    return snapped;
}

static void
modelAdjustObjectsForShiver (Model *model,
			     int   x,
			     int   y,
			     int   width,
			     int   height)
{
    int   gridX, gridY, i = 0;
    float vX, vY;
    float w, h;
    float scale;

    w = width;
    h = height;

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    if (!model->objects[i].immobile)
	    {
		vX = model->objects[i].position.x - (x + w / 2);
		vY = model->objects[i].position.y - (y + h / 2);

		vX /= w;
		vY /= h;

		scale = ((float) rand () * 7.5f) / RAND_MAX;

		model->objects[i].velocity.x += vX * scale;
		model->objects[i].velocity.y += vY * scale;
	    }

	    i++;
	}
    }
}

static void
modelInitSprings (Model *model,
		  int   x,
		  int   y,
		  int   width,
		  int   height)
{
    int   gridX, gridY, i = 0;
    float hpad, vpad;

    model->numSprings = 0;

    hpad = ((float) width) / (GRID_WIDTH  - 1);
    vpad = ((float) height) / (GRID_HEIGHT - 1);

    for (gridY = 0; gridY < GRID_HEIGHT; gridY++)
    {
	for (gridX = 0; gridX < GRID_WIDTH; gridX++)
	{
	    if (gridX > 0)
		modelAddSpring (model,
				&model->objects[i - 1],
				&model->objects[i],
				hpad, 0);

	    if (gridY > 0)
		modelAddSpring (model,
				&model->objects[i - GRID_WIDTH],
				&model->objects[i],
				0, vpad);

	    i++;
	}
    }
}

static void
modelMove (Model *model,
	   float tx,
	   float ty)
{
    int i;

    for (i = 0; i < model->numObjects; i++)
    {
	model->objects[i].position.x += tx;
	model->objects[i].position.y += ty;
    }
}

static Model *
createModel (int	  x,
	     int	  y,
	     int	  width,
	     int	  height,
	     unsigned int edgeMask)
{
    Model *model;

    model = static_cast<Model*>(calloc (1, sizeof (Model)));
    if (!model)
	return 0;

    model->numObjects = GRID_WIDTH * GRID_HEIGHT;
    model->objects = static_cast<Object*>(calloc (model->numObjects, sizeof (Object)));
    if (!model->objects)
    {
	free (model);
	return 0;
    }

    model->anchorObject = 0;
    model->numSprings = 0;

    model->steps = 0;

    memset (model->snapCnt, 0, sizeof (model->snapCnt));

    model->edgeMask = edgeMask;

    modelInitObjects (model, x, y, width, height);
    modelInitSprings (model, x, y, width, height);

    modelCalcBounds (model);

    return model;
}

static void
objectApplyForce (Object *object,
		  float  fx,
		  float  fy)
{
    object->force.x += fx;
    object->force.y += fy;
}

static void
springExertForces (Spring *spring,
		   float  k)
{
    Vector da, db;
    Vector a, b;

    a = spring->a->position;
    b = spring->b->position;

    da.x = 0.5f * (b.x - a.x - spring->offset.x);
    da.y = 0.5f * (b.y - a.y - spring->offset.y);

    db.x = 0.5f * (a.x - b.x + spring->offset.x);
    db.y = 0.5f * (a.y - b.y + spring->offset.y);

    objectApplyForce (spring->a, k * da.x, k * da.y);
    objectApplyForce (spring->b, k * db.x, k * db.y);
}

static Bool
objectReleaseWestEdge (CompWindow *w,
		       Model	  *model,
		       Object	  *object)
{
    if (fabs (object->velocity.x) > object->vertEdge.velocity)
    {
	object->position.x += object->velocity.x * 2.0f;

	model->snapCnt[WEST]--;

	object->vertEdge.snapped = FALSE;
	object->edgeMask = 0;

	modelUpdateSnapping (w, model);

	return TRUE;
    }

    object->velocity.x = 0.0f;

    return FALSE;
}

static Bool
objectReleaseEastEdge (CompWindow *w,
		       Model	  *model,
		       Object	  *object)
{
    if (fabs (object->velocity.x) > object->vertEdge.velocity)
    {
	object->position.x += object->velocity.x * 2.0f;

	model->snapCnt[EAST]--;

	object->vertEdge.snapped = FALSE;
	object->edgeMask = 0;

	modelUpdateSnapping (w, model);

	return TRUE;
    }

    object->velocity.x = 0.0f;

    return FALSE;
}

static Bool
objectReleaseNorthEdge (CompWindow *w,
			Model	   *model,
			Object	   *object)
{
    if (fabs (object->velocity.y) > object->horzEdge.velocity)
    {
	object->position.y += object->velocity.y * 2.0f;

	model->snapCnt[NORTH]--;

	object->horzEdge.snapped = FALSE;
	object->edgeMask = 0;

	modelUpdateSnapping (w, model);

	return TRUE;
    }

    object->velocity.y = 0.0f;

    return FALSE;
}

static Bool
objectReleaseSouthEdge (CompWindow *w,
			Model	   *model,
			Object	   *object)
{
    if (fabs (object->velocity.y) > object->horzEdge.velocity)
    {
	object->position.y += object->velocity.y * 2.0f;

	model->snapCnt[SOUTH]--;

	object->horzEdge.snapped = FALSE;
	object->edgeMask = 0;

	modelUpdateSnapping (w, model);

	return TRUE;
    }

    object->velocity.y = 0.0f;

    return FALSE;
}

static float
modelStepObject (CompWindow *window,
		 Model	    *model,
		 Object	    *object,
		 float	    friction,
		 float	    *force)
{
    object->theta += 0.05f;

    if (object->immobile)
    {
	object->velocity.x = 0.0f;
	object->velocity.y = 0.0f;

	object->force.x = 0.0f;
	object->force.y = 0.0f;

	*force = 0.0f;

	return 0.0f;
    }
    else
    {
	object->force.x -= friction * object->velocity.x;
	object->force.y -= friction * object->velocity.y;

	object->velocity.x += object->force.x / MASS;
	object->velocity.y += object->force.y / MASS;

	if (object->edgeMask)
	{
	    if (object->edgeMask & WestEdgeMask)
	    {
		if (object->position.y < object->vertEdge.start ||
		    object->position.y > object->vertEdge.end)
		    findNextWestEdge (window, object);

		if (!object->vertEdge.snapped ||
		    objectReleaseWestEdge (window, model, object))
		{
		    object->position.x += object->velocity.x;

		    if (object->velocity.x < 0.0f &&
			object->position.x < object->vertEdge.attract)
		    {
			if (object->position.x < object->vertEdge.next)
			{
			    object->vertEdge.snapped = TRUE;
			    object->position.x = object->vertEdge.next;
			    object->velocity.x = 0.0f;

			    model->snapCnt[WEST]++;

			    modelUpdateSnapping (window, model);
			}
			else
			{
			    object->velocity.x -=
				object->vertEdge.attract - object->position.x;
			}
		    }

		    if (object->position.x > object->vertEdge.prev)
			findNextWestEdge (window, object);
		}
	    }
	    else if (object->edgeMask & EastEdgeMask)
	    {
		if (object->position.y < object->vertEdge.start ||
		    object->position.y > object->vertEdge.end)
		    findNextEastEdge (window, object);

		if (!object->vertEdge.snapped ||
		    objectReleaseEastEdge (window, model, object))
		{
		    object->position.x += object->velocity.x;

		    if (object->velocity.x > 0.0f &&
			object->position.x > object->vertEdge.attract)
		    {
			if (object->position.x > object->vertEdge.next)
			{
			    object->vertEdge.snapped = TRUE;
			    object->position.x = object->vertEdge.next;
			    object->velocity.x = 0.0f;

			    model->snapCnt[EAST]++;

			    modelUpdateSnapping (window, model);
			}
			else
			{
			    object->velocity.x =
				object->position.x - object->vertEdge.attract;
			}
		    }

		    if (object->position.x < object->vertEdge.prev)
			findNextEastEdge (window, object);
		}
	    }
	    else
		object->position.x += object->velocity.x;

	    if (object->edgeMask & NorthEdgeMask)
	    {
		if (object->position.x < object->horzEdge.start ||
		    object->position.x > object->horzEdge.end)
		    findNextNorthEdge (window, object);

		if (!object->horzEdge.snapped ||
		    objectReleaseNorthEdge (window, model, object))
		{
		    object->position.y += object->velocity.y;

		    if (object->velocity.y < 0.0f &&
			object->position.y < object->horzEdge.attract)
		    {
			if (object->position.y < object->horzEdge.next)
			{
			    object->horzEdge.snapped = TRUE;
			    object->position.y = object->horzEdge.next;
			    object->velocity.y = 0.0f;

			    model->snapCnt[NORTH]++;

			    modelUpdateSnapping (window, model);
			}
			else
			{
			    object->velocity.y -=
				object->horzEdge.attract - object->position.y;
			}
		    }

		    if (object->position.y > object->horzEdge.prev)
			findNextNorthEdge (window, object);
		}
	    }
	    else if (object->edgeMask & SouthEdgeMask)
	    {
		if (object->position.x < object->horzEdge.start ||
		    object->position.x > object->horzEdge.end)
		    findNextSouthEdge (window, object);

		if (!object->horzEdge.snapped ||
		    objectReleaseSouthEdge (window, model, object))
		{
		    object->position.y += object->velocity.y;

		    if (object->velocity.y > 0.0f &&
			object->position.y > object->horzEdge.attract)
		    {
			if (object->position.y > object->horzEdge.next)
			{
			    object->horzEdge.snapped = TRUE;
			    object->position.y = object->horzEdge.next;
			    object->velocity.y = 0.0f;

			    model->snapCnt[SOUTH]++;

			    modelUpdateSnapping (window, model);
			}
			else
			{
			    object->velocity.y =
				object->position.y - object->horzEdge.attract;
			}
		    }

		    if (object->position.y < object->horzEdge.prev)
			findNextSouthEdge (window, object);
		}
	    }
	    else
		object->position.y += object->velocity.y;
	}
	else
	{
	    object->position.x += object->velocity.x;
	    object->position.y += object->velocity.y;
	}

	*force = fabs (object->force.x) + fabs (object->force.y);

	object->force.x = 0.0f;
	object->force.y = 0.0f;

	return fabs (object->velocity.x) + fabs (object->velocity.y);
    }
}

static int
modelStep (CompWindow *window,
	   Model      *model,
	   float      friction,
	   float      k,
	   float      time)
{
    int   i, j, steps, wobbly = 0;
    float velocitySum = 0.0f;
    float force, forceSum = 0.0f;

    model->steps += time / 15.0f;
    steps = floor (model->steps);
    model->steps -= steps;

    if (!steps)
	return TRUE;

    for (j = 0; j < steps; j++)
    {
	for (i = 0; i < model->numSprings; i++)
	    springExertForces (&model->springs[i], k);

	for (i = 0; i < model->numObjects; i++)
	{
	    velocitySum += modelStepObject (window,
					    model,
					    &model->objects[i],
					    friction,
					    &force);
	    forceSum += force;
	}
    }

    modelCalcBounds (model);

    if (velocitySum > 0.5f)
	wobbly |= WobblyVelocity;

    if (forceSum > 20.0f)
	wobbly |= WobblyForce;

    return wobbly;
}

static void
bezierPatchEvaluate (Model *model,
		     float u,
		     float v,
		     float *patchX,
		     float *patchY)
{
    float coeffsU[4], coeffsV[4];
    float x, y;
    int   i, j;

    coeffsU[0] = (1 - u) * (1 - u) * (1 - u);
    coeffsU[1] = 3 * u * (1 - u) * (1 - u);
    coeffsU[2] = 3 * u * u * (1 - u);
    coeffsU[3] = u * u * u;

    coeffsV[0] = (1 - v) * (1 - v) * (1 - v);
    coeffsV[1] = 3 * v * (1 - v) * (1 - v);
    coeffsV[2] = 3 * v * v * (1 - v);
    coeffsV[3] = v * v * v;

    x = y = 0.0f;

    for (i = 0; i < 4; i++)
    {
	for (j = 0; j < 4; j++)
	{
	    x += coeffsU[i] * coeffsV[j] *
		model->objects[j * GRID_WIDTH + i].position.x;
	    y += coeffsU[i] * coeffsV[j] *
		model->objects[j * GRID_WIDTH + i].position.y;
	}
    }

    *patchX = x;
    *patchY = y;
}

static float
objectDistance (Object *object,
		float  x,
		float  y)
{
    float dx, dy;

    dx = object->position.x - x;
    dy = object->position.y - y;

    return sqrt (dx * dx + dy * dy);
}

static Object *
modelFindNearestObject (Model *model,
			float x,
			float y)
{
    Object *object = &model->objects[0];
    float  distance, minDistance = 0.0;
    int    i;

    for (i = 0; i < model->numObjects; i++)
    {
	distance = objectDistance (&model->objects[i], x, y);
	if (i == 0 || distance < minDistance)
	{
	    minDistance = distance;
	    object = &model->objects[i];
	}
    }

    return object;
}


} // namespace Wobbly::Compiz
